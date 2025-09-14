import asyncio
import websockets
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import aiohttp
from colorama import init, Fore, Style, Back
from pathlib import Path
import base58
import base64
from solana.rpc.api import Client
from solana.transaction import Transaction
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
import httpx
import hashlib
import time

init(autoreset=True)

# Configuration storage path
CONFIG_DIR = Path.home() / ".augmentry_sniper"
CONFIG_FILE = CONFIG_DIR / "config.json"
WALLETS_FILE = CONFIG_DIR / "wallets.json"

# ============================================
# CONFIGURATION
# ============================================
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
SWAP_API_BASE = "https://swap-v2.augmentry.io"
STREAM_WS_URL = "wss://stream.augmentry.io/api/data"
DATA_API_BASE = "https://data.augmentry.io"

class FilterType(Enum):
    MIN_LIQUIDITY = "min_liquidity"
    MAX_LIQUIDITY = "max_liquidity"
    MIN_MARKET_CAP = "min_market_cap"
    MAX_MARKET_CAP = "max_market_cap"
    NAME_CONTAINS = "name_contains"
    NAME_EXCLUDES = "name_excludes"
    SYMBOL_CONTAINS = "symbol_contains"
    SYMBOL_EXCLUDES = "symbol_excludes"
    MIN_HOLDERS = "min_holders"
    VERIFIED_ONLY = "verified_only"

@dataclass
class SniperConfig:
    """Configuration for token sniping"""
    enabled: bool = False
    auto_buy: bool = False
    buy_amount_sol: float = 0.025
    slippage: float = 10.0
    priority_fee: float = 0.0005
    priority_fee_level: str = "medium"  # min, low, medium, high, veryHigh, unsafeMax
    max_retries: int = 3
    filters: Dict[str, Any] = field(default_factory=dict)
    
    # Advanced settings
    take_profit: float = 50.0  # % gain to auto-sell
    stop_loss: float = 20.0    # % loss to auto-sell
    trail_stop: bool = False
    max_position_sol: float = 1.0
    webhook_url: Optional[str] = None
    use_auto_slippage: bool = True  # Use dynamic slippage
    use_auto_priority: bool = False  # Use auto priority fee
    custom_api_key: Optional[str] = None  # Optional API key
    
@dataclass
class WalletConfig:
    """Wallet configuration"""
    address: str
    private_key: str = ""  # Encrypted in real implementation
    is_default: bool = False
    label: str = ""

class TokenSniper:
    """Main token sniper application"""
    
    def __init__(self):
        self.config = SniperConfig()
        self.wallets: List[WalletConfig] = []
        self.websocket = None
        self.running = False
        self.matched_tokens = []
        self.positions = {}
        self.connection = Client(SOLANA_RPC)
        self.stats = {
            "tokens_analyzed": 0,
            "tokens_matched": 0,
            "trades_executed": 0,
            "trades_failed": 0,
            "profit_total": 0.0
        }
        
    async def initialize(self):
        """Initialize configuration directory and load settings"""
        CONFIG_DIR.mkdir(exist_ok=True)
        await self.load_config()
        
        print(f"{Fore.CYAN}✓ Augmentry Tools initialized{Style.RESET_ALL}")
        print(f"  • Swap API: {SWAP_API_BASE}")
        print(f"  • Stream WS: {STREAM_WS_URL}")
        
    async def load_config(self):
        """Load configuration from file"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.config = SniperConfig(**data)
                print(f"{Fore.GREEN}✓ Configuration loaded{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}⚠ Could not load config: {e}{Style.RESET_ALL}")
                
        if WALLETS_FILE.exists():
            try:
                with open(WALLETS_FILE, 'r') as f:
                    wallets_data = json.load(f)
                    self.wallets = [WalletConfig(**w) for w in wallets_data]
                print(f"{Fore.GREEN}✓ {len(self.wallets)} wallet(s) loaded{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}⚠ Could not load wallets: {e}{Style.RESET_ALL}")
    
    async def save_config(self):
        """Save configuration to file"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(asdict(self.config), f, indent=2)
            
            wallets_data = [asdict(w) for w in self.wallets]
            with open(WALLETS_FILE, 'w') as f:
                json.dump(wallets_data, f, indent=2)
                
            print(f"{Fore.GREEN}✓ Configuration saved{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Error saving config: {e}{Style.RESET_ALL}")
    
    def parse_private_key(self, private_key_str: str) -> Optional[Keypair]:
        """Parse private key from various formats"""
        try:
            private_key_str = private_key_str.strip()
            
            # Try base58 format first (most common)
            try:
                private_key_bytes = base58.b58decode(private_key_str)
                if len(private_key_bytes) == 64:
                    return Keypair.from_bytes(private_key_bytes)
                elif len(private_key_bytes) == 32:
                    return Keypair.from_seed(private_key_bytes[:32])
            except:
                pass
            
            # Try hex format
            try:
                private_key_bytes = bytes.fromhex(private_key_str)
                if len(private_key_bytes) == 64:
                    return Keypair.from_bytes(private_key_bytes)
                elif len(private_key_bytes) == 32:
                    return Keypair.from_seed(private_key_bytes[:32])
            except:
                pass
            
            # Try JSON array format [1,2,3,...]
            try:
                import ast
                if private_key_str.startswith('[') and private_key_str.endswith(']'):
                    key_array = ast.literal_eval(private_key_str)
                    private_key_bytes = bytes(key_array)
                    if len(private_key_bytes) == 64:
                        return Keypair.from_bytes(private_key_bytes)
                    elif len(private_key_bytes) == 32:
                        return Keypair.from_seed(private_key_bytes[:32])
            except:
                pass
            
            # Try comma-separated format
            try:
                key_array = [int(x.strip()) for x in private_key_str.split(',') if x.strip()]
                private_key_bytes = bytes(key_array)
                if len(private_key_bytes) == 64:
                    return Keypair.from_bytes(private_key_bytes)
                elif len(private_key_bytes) == 32:
                    return Keypair.from_seed(private_key_bytes[:32])
            except:
                pass
            
            return None
            
        except Exception as e:
            print(f"{Fore.RED}Error parsing private key: {e}{Style.RESET_ALL}")
            return None
    
    def check_token_filters(self, token_data: Dict) -> bool:
        """Check if token matches configured filters"""
        filters = self.config.filters
        
        # Market cap filters
        if "min_market_cap" in filters:
            market_cap = token_data.get("marketCapSol", 0)
            if market_cap < filters["min_market_cap"]:
                return False
                
        if "max_market_cap" in filters:
            market_cap = token_data.get("marketCapSol", 0)
            if market_cap > filters["max_market_cap"]:
                return False
        
        # Liquidity filters
        if "min_liquidity" in filters:
            liquidity = token_data.get("vSolInBondingCurve", 0)
            if liquidity < filters["min_liquidity"]:
                return False
                
        # Name/Symbol filters
        name = token_data.get("name", "").lower()
        symbol = token_data.get("symbol", "").lower()
        
        if "name_contains" in filters:
            keywords = filters["name_contains"]
            if not any(kw.lower() in name for kw in keywords):
                return False
                
        if "name_excludes" in filters:
            blacklist = filters["name_excludes"]
            if any(word.lower() in name for word in blacklist):
                return False
                
        if "symbol_contains" in filters:
            keywords = filters["symbol_contains"]
            if not any(kw.lower() in symbol for kw in keywords):
                return False
                
        if "symbol_excludes" in filters:
            blacklist = filters["symbol_excludes"]
            if any(word.lower() in symbol for word in blacklist):
                return False
        
        return True
    
    async def execute_trade(self, token_data: Dict):
        """Execute a trade using Augmentry Swap API"""
        if not self.config.auto_buy:
            print(f"{Fore.YELLOW}Auto-buy disabled. Token matched but not buying.{Style.RESET_ALL}")
            return
            
        if not self.wallets:
            print(f"{Fore.RED}No wallet configured!{Style.RESET_ALL}")
            return
            
        default_wallet = next((w for w in self.wallets if w.is_default), self.wallets[0])
        
        if not default_wallet.private_key:
            print(f"{Fore.RED}No private key configured for trading!{Style.RESET_ALL}")
            return
        
        # Parse the private key
        keypair = self.parse_private_key(default_wallet.private_key)
        if not keypair:
            print(f"{Fore.RED}Failed to parse private key!{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Supported formats:{Style.RESET_ALL}")
            print(f"  • Base58 encoded (e.g., 5JuE...)")
            print(f"  • Hexadecimal (e.g., a1b2c3...)")
            print(f"  • JSON array (e.g., [128,32,15...])")
            print(f"  • Comma-separated (e.g., 128,32,15...)")
            return
        
        wallet_pubkey = str(keypair.pubkey())
        
        print(f"\n{Fore.CYAN}🎯 Executing trade via Augmentry Swap API...{Style.RESET_ALL}")
        print(f"  Token: {token_data.get('symbol', 'Unknown')}")
        print(f"  Mint: {token_data.get('mint', 'Unknown')}")
        print(f"  Amount: {self.config.buy_amount_sol} SOL")
        print(f"  Slippage: {'auto' if self.config.use_auto_slippage else str(self.config.slippage) + '%'}")
        print(f"  Wallet: {wallet_pubkey[:8]}...{wallet_pubkey[-6:]}")
        print(f"  Using: {SWAP_API_BASE}")
        
        try:
            # Build swap URL with parameters
            params = {
                "from": "So11111111111111111111111111111111111111112",  # SOL
                "to": token_data.get("mint"),
                "amount": str(self.config.buy_amount_sol),
                "slippage": "auto" if self.config.use_auto_slippage else str(self.config.slippage),
                "payer": wallet_pubkey
            }
            
            # Add optional parameters
            if self.config.use_auto_priority:
                params["priorityFee"] = "auto"
                params["priorityFeeLevel"] = self.config.priority_fee_level
            elif self.config.priority_fee > 0:
                params["priorityFee"] = str(self.config.priority_fee)
            
            # Build URL with query parameters
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            swap_url = f"{SWAP_API_BASE}/swap?{query_string}"
            
            print(f"{Fore.YELLOW}⏳ Requesting swap transaction from Augmentry API...{Style.RESET_ALL}")
            
            # Prepare headers with optional API key
            headers = {}
            if self.config.custom_api_key:
                headers["x-api-key"] = self.config.custom_api_key
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get swap transaction from API
                response = await client.get(swap_url, headers=headers)
                
                if response.status_code != 200:
                    print(f"{Fore.RED}✗ API Error: {response.text}{Style.RESET_ALL}")
                    self.stats["trades_failed"] += 1
                    return
                
                swap_data = response.json()
                
                if "txn" not in swap_data:
                    print(f"{Fore.RED}✗ No transaction returned: {swap_data}{Style.RESET_ALL}")
                    self.stats["trades_failed"] += 1
                    return
                
                # Display swap details
                if "rate" in swap_data:
                    rate = swap_data["rate"]
                    print(f"\n{Fore.CYAN}📊 Swap Details:{Style.RESET_ALL}")
                    print(f"  Amount In: {rate.get('amountIn', 0)} SOL")
                    print(f"  Expected Out: {rate.get('amountOut', 0)} tokens")
                    print(f"  Min Out: {rate.get('minAmountOut', 0)} tokens")
                    print(f"  Price Impact: {rate.get('priceImpact', 0) * 100:.4f}%")
                    print(f"  Platform Fee: {rate.get('platformFeeUI', 0)} SOL")
                
                # Debug: Print what we received
                print(f"\n{Fore.YELLOW}Debug - Transaction data type: {type(swap_data.get('txn'))}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Debug - Transaction preview: {str(swap_data.get('txn'))[:100]}...{Style.RESET_ALL}")
                
                # Deserialize transaction - try base64 first, then base58
                txn_data = swap_data["txn"]
                try:
                    # Most APIs return base64 encoded transactions
                    tx_bytes = base64.b64decode(txn_data)
                    print(f"{Fore.GREEN}✓ Successfully decoded as base64{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.YELLOW}Base64 decode failed, trying base58...{Style.RESET_ALL}")
                    try:
                        tx_bytes = base58.b58decode(txn_data)
                        print(f"{Fore.GREEN}✓ Successfully decoded as base58{Style.RESET_ALL}")
                    except Exception as e2:
                        print(f"{Fore.RED}✗ Failed to decode transaction data{Style.RESET_ALL}")
                        print(f"Base64 error: {e}")
                        print(f"Base58 error: {e2}")
                        raise ValueError(f"Could not decode transaction: {e2}")
                
                if swap_data.get("type") == "v0":
                    # Versioned transaction
                    txn = VersionedTransaction.from_bytes(tx_bytes)
                    print(f"{Fore.YELLOW}⏳ Signing versioned transaction...{Style.RESET_ALL}")
                    
                    # Sign the transaction
                    txn.sign([keypair])
                    
                    # Serialize signed transaction
                    signed_tx = bytes(txn)
                else:
                    # Legacy transaction
                    txn = Transaction.deserialize(tx_bytes)
                    print(f"{Fore.YELLOW}⏳ Signing legacy transaction...{Style.RESET_ALL}")
                    
                    # Sign the transaction
                    txn.sign(keypair)
                    
                    # Serialize signed transaction
                    signed_tx = txn.serialize()
                
                # Send transaction
                print(f"{Fore.YELLOW}⏳ Sending transaction to blockchain...{Style.RESET_ALL}")
                
                # Use Solana RPC to send transaction
                send_response = await client.post(
                    SOLANA_RPC,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "sendTransaction",
                        "params": [
                            base58.b58encode(signed_tx).decode('ascii'),
                            {
                                "skipPreflight": True,
                                "preflightCommitment": "confirmed",
                                "encoding": "base58",
                                "maxRetries": self.config.max_retries
                            }
                        ]
                    },
                    headers={"Content-Type": "application/json"}
                )
                
                result = send_response.json()
                
                if "result" in result:
                    tx_hash = result["result"]
                    
                    print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}✅ TRADE EXECUTED SUCCESSFULLY!{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}📝 Transaction Hash:{Style.RESET_ALL}")
                    print(f"   {Fore.WHITE}{tx_hash}{Style.RESET_ALL}")
                    print(f"{Fore.BLUE}🔗 View on Solscan:{Style.RESET_ALL}")
                    print(f"   https://solscan.io/tx/{tx_hash}")
                    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
                    
                    self.stats["trades_executed"] += 1
                    
                    # Track position
                    self.positions[token_data.get("mint")] = {
                        "symbol": token_data.get("symbol"),
                        "name": token_data.get("name"),
                        "entry_price": token_data.get("marketCapSol", 0),
                        "amount_sol": self.config.buy_amount_sol,
                        "amount_tokens": swap_data.get("rate", {}).get("amountOut", 0),
                        "timestamp": datetime.now().isoformat(),
                        "tx_hash": tx_hash,
                        "status": "pending"
                    }
                    
                    # Send webhook notification if configured
                    if self.config.webhook_url:
                        await self.send_webhook_notification(token_data, {
                            "wallet": wallet_pubkey,
                            "amount_sol": self.config.buy_amount_sol,
                            "tx_hash": tx_hash,
                            "solscan_url": f"https://solscan.io/tx/{tx_hash}",
                            "expected_tokens": swap_data.get("rate", {}).get("amountOut", 0)
                        })
                    
                    # Wait for confirmation
                    print(f"{Fore.YELLOW}⏳ Waiting for blockchain confirmation...{Style.RESET_ALL}")
                    confirmed = await self.wait_for_confirmation(tx_hash)
                    
                    if confirmed:
                        print(f"{Fore.GREEN}✅ Transaction confirmed on blockchain!{Style.RESET_ALL}")
                        self.positions[token_data.get("mint")]["status"] = "confirmed"
                    else:
                        print(f"{Fore.YELLOW}⚠️ Transaction confirmation timeout (may still succeed){Style.RESET_ALL}")
                    
                else:
                    error_msg = result.get("error", {}).get("message", "Unknown error")
                    print(f"{Fore.RED}✗ Transaction failed: {error_msg}{Style.RESET_ALL}")
                    self.stats["trades_failed"] += 1
                    
        except Exception as e:
            print(f"{Fore.RED}✗ Trade execution error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            self.stats["trades_failed"] += 1

    async def wait_for_confirmation(self, tx_hash: str, max_attempts: int = 30):
        """Wait for transaction confirmation"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(max_attempts):
                try:
                    response = await client.post(
                        SOLANA_RPC,
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "getSignatureStatuses",
                            "params": [[tx_hash]]
                        },
                        headers={"Content-Type": "application/json"}
                    )
                    
                    result = response.json()
                    if "result" in result and result["result"]["value"]:
                        status = result["result"]["value"][0]
                        if status:
                            confirmation_status = status.get("confirmationStatus")
                            if confirmation_status in ["confirmed", "finalized"]:
                                return True
                            elif status.get("err"):
                                print(f"{Fore.RED}Transaction failed: {status.get('err')}{Style.RESET_ALL}")
                                return False
                        
                    await asyncio.sleep(1)
                    if attempt % 5 == 0:
                        print(f"{Fore.YELLOW}Still waiting... ({attempt}/{max_attempts}){Style.RESET_ALL}")
                    
                except Exception as e:
                    if attempt % 10 == 0:
                        print(f"{Fore.YELLOW}Confirmation check error: {e}{Style.RESET_ALL}")
                    
            return False
    
    async def send_webhook_notification(self, token_data: Dict, trade_params: Dict):
        """Send webhook notification for trade"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "event": "token_sniped",
                    "token": {
                        "name": token_data.get("name"),
                        "symbol": token_data.get("symbol"),
                        "mint": token_data.get("mint"),
                        "market_cap_sol": token_data.get("marketCapSol"),
                        "liquidity_sol": token_data.get("vSolInBondingCurve")
                    },
                    "trade": trade_params,
                    "timestamp": datetime.now().isoformat()
                }
                await session.post(self.config.webhook_url, json=payload)
                print(f"{Fore.GREEN}✓ Webhook notification sent{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}Webhook notification failed: {e}{Style.RESET_ALL}")
    
    async def monitor_tokens(self):
        """Main monitoring loop"""
        uri = STREAM_WS_URL
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}🚀 STARTING TOKEN MONITOR{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"Stream: {uri}")
        print(f"Filters active: {len(self.config.filters)}")
        print(f"Auto-buy: {Fore.GREEN if self.config.auto_buy else Fore.RED}{self.config.auto_buy}{Style.RESET_ALL}")
        print(f"Buy amount: {self.config.buy_amount_sol} SOL")
        print(f"Slippage: {'auto' if self.config.use_auto_slippage else str(self.config.slippage) + '%'}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        try:
            # Add headers if API key is configured
            headers = {}
            if self.config.custom_api_key:
                headers["x-api-key"] = self.config.custom_api_key
            
            # Create connection with proper headers handling for websockets v15+
            connect_kwargs = {"uri": uri}
            if headers:
                connect_kwargs["additional_headers"] = headers
            
            async with websockets.connect(**connect_kwargs) as websocket:
                self.websocket = websocket
                print(f"{Fore.GREEN}✓ Connected to Augmentry Stream WebSocket{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Monitoring for new tokens...{Style.RESET_ALL}\n")
                
                # Subscribe to new tokens
                await websocket.send(json.dumps({"method": "subscribeNewToken"}))
                
                self.running = True
                
                async for message in websocket:
                    if not self.running:
                        break
                        
                    try:
                        data = json.loads(message)
                        
                        # Process new token creation
                        if data.get("txType") == "create":
                            self.stats["tokens_analyzed"] += 1
                            
                            # Check filters
                            if self.check_token_filters(data):
                                self.stats["tokens_matched"] += 1
                                
                                print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                                print(f"{Fore.CYAN}🎯 TOKEN MATCH FOUND!{Style.RESET_ALL}")
                                print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                                print(f"Name: {Fore.WHITE}{data.get('name', 'Unknown')}{Style.RESET_ALL}")
                                print(f"Symbol: {Fore.WHITE}{data.get('symbol', 'Unknown')}{Style.RESET_ALL}")
                                print(f"Mint: {Fore.WHITE}{data.get('mint', 'Unknown')}{Style.RESET_ALL}")
                                print(f"Market Cap: {Fore.YELLOW}{data.get('marketCapSol', 0):.4f} SOL{Style.RESET_ALL}")
                                print(f"Liquidity: {Fore.YELLOW}{data.get('vSolInBondingCurve', 0):.4f} SOL{Style.RESET_ALL}")
                                print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                                
                                self.matched_tokens.append(data)
                                
                                # Execute trade if auto-buy is enabled
                                await self.execute_trade(data)
                                
                            # Show progress
                            if self.stats["tokens_analyzed"] % 10 == 0:
                                print(f"\r{Fore.YELLOW}📊 Analyzed: {self.stats['tokens_analyzed']} | Matched: {self.stats['tokens_matched']} | Executed: {self.stats['trades_executed']} | Failed: {self.stats['trades_failed']}{Style.RESET_ALL}", end="")
                                
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        print(f"\n{Fore.RED}Error processing message: {e}{Style.RESET_ALL}")
                        
        except Exception as e:
            print(f"\n{Fore.RED}WebSocket error: {e}{Style.RESET_ALL}")
        finally:
            self.running = False
            print(f"\n{Fore.YELLOW}Monitor stopped{Style.RESET_ALL}")

    def display_main_menu(self):
        """Display main menu"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\n{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}🚀 Augmentry Tools - Sniper Bot v1.0{Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
        
        print(f"{Fore.GREEN}✓ System Ready{Style.RESET_ALL}")
        print(f"  API: {SWAP_API_BASE}")
        print(f"  Stream: {STREAM_WS_URL}\n")
        
        status = f"{Fore.GREEN}ACTIVE{Style.RESET_ALL}" if self.config.enabled else f"{Fore.RED}INACTIVE{Style.RESET_ALL}"
        print(f"Status: {status}")
        print(f"Wallets: {len(self.wallets)}")
        print(f"Filters: {len(self.config.filters)}")
        print(f"Auto-buy: {self.config.auto_buy}")
        print(f"Buy amount: {self.config.buy_amount_sol} SOL")
        print(f"Slippage: {'auto' if self.config.use_auto_slippage else str(self.config.slippage) + '%'}\n")
        
        # Show quick stats
        if self.stats["tokens_analyzed"] > 0:
            print(f"{Fore.CYAN}Session Stats:{Style.RESET_ALL}")
            print(f"  Analyzed: {self.stats['tokens_analyzed']}")
            print(f"  Matched: {self.stats['tokens_matched']}")
            print(f"  Executed: {self.stats['trades_executed']}")
            print(f"  Failed: {self.stats['trades_failed']}\n")
        
        print(f"{Fore.YELLOW}Main Menu:{Style.RESET_ALL}")
        print("1. 📊 Start Monitoring")
        print("2. ⚙️  Configure Filters")
        print("3. 👛 Manage Wallets")
        print("4. 💰 Trading Settings")
        print("5. 📈 View Statistics & Positions")
        print("6. 🔧 Advanced Settings")
        print("7. 🔑 API Settings")
        print("8. 💾 Save Configuration")
        print("9. ❌ Exit")
        
    def api_settings_menu(self):
        """Configure API settings"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{Fore.CYAN}API Settings{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
            
            print(f"Custom API Key: {'Set' if self.config.custom_api_key else 'Not set'}")
            print(f"\nEndpoints:")
            print(f"  Swap API: {SWAP_API_BASE}")
            print(f"  Stream WS: {STREAM_WS_URL}")
            print(f"  Data API: {DATA_API_BASE}")
            
            print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
            print("1. Set Custom API Key")
            print("2. Test API Connection")
            print("3. Back to Main Menu")
            
            choice = input(f"\n{Fore.CYAN}Select option: {Style.RESET_ALL}")
            
            if choice == "1":
                api_key = input("Custom API Key (leave empty to clear): ").strip()
                self.config.custom_api_key = api_key if api_key else None
                print(f"{Fore.GREEN}✓ API Key updated{Style.RESET_ALL}")
                
            elif choice == "2":
                print(f"\n{Fore.YELLOW}Testing API connections...{Style.RESET_ALL}")
                asyncio.run(self.test_api_connections())
                
            elif choice == "3":
                break
                
            if choice in ["1", "2"]:
                input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
    
    async def test_api_connections(self):
        """Test connections to APIs"""
        headers = {}
        if self.config.custom_api_key:
            headers["x-api-key"] = self.config.custom_api_key
        
        # Test Swap API
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{SWAP_API_BASE}/", headers=headers)
                if response.status_code in [200, 404]:  # 404 is ok for root path
                    print(f"{Fore.GREEN}✓ Swap API reachable{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}⚠ Swap API returned status {response.status_code}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Swap API error: {e}{Style.RESET_ALL}")
        
        # Test WebSocket
        try:
            connect_kwargs = {"uri": STREAM_WS_URL}
            if headers:
                connect_kwargs["additional_headers"] = headers
            async with websockets.connect(**connect_kwargs) as ws:
                print(f"{Fore.GREEN}✓ WebSocket stream connected{Style.RESET_ALL}")
                await ws.close()
        except Exception as e:
            print(f"{Fore.RED}✗ WebSocket error: {e}{Style.RESET_ALL}")
        
        # Test Data API if configured
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{DATA_API_BASE}/", headers=headers)
                if response.status_code in [200, 404]:
                    print(f"{Fore.GREEN}✓ Data API reachable{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}⚠ Data API returned status {response.status_code}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}✗ Data API error: {e}{Style.RESET_ALL}")
    
    def configure_filters_menu(self):
        """Configure token filters"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{Fore.CYAN}Filter Configuration{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
            
            print(f"{Fore.YELLOW}Current Filters:{Style.RESET_ALL}")
            if not self.config.filters:
                print("  No filters configured")
            else:
                for key, value in self.config.filters.items():
                    print(f"  • {key}: {value}")
            
            print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
            print("1. Set Minimum Market Cap (SOL)")
            print("2. Set Maximum Market Cap (SOL)")
            print("3. Set Minimum Liquidity (SOL)")
            print("4. Add Name Contains Keywords")
            print("5. Add Name Excludes Keywords")
            print("6. Add Symbol Contains Keywords")
            print("7. Add Symbol Excludes Keywords")
            print("8. Clear All Filters")
            print("9. Back to Main Menu")
            
            choice = input(f"\n{Fore.CYAN}Select option: {Style.RESET_ALL}")
            
            if choice == "1":
                try:
                    value = float(input("Minimum market cap (SOL): "))
                    self.config.filters["min_market_cap"] = value
                    print(f"{Fore.GREEN}✓ Filter added{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}Invalid value{Style.RESET_ALL}")
                    
            elif choice == "2":
                try:
                    value = float(input("Maximum market cap (SOL): "))
                    self.config.filters["max_market_cap"] = value
                    print(f"{Fore.GREEN}✓ Filter added{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}Invalid value{Style.RESET_ALL}")
                    
            elif choice == "3":
                try:
                    value = float(input("Minimum liquidity (SOL): "))
                    self.config.filters["min_liquidity"] = value
                    print(f"{Fore.GREEN}✓ Filter added{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}Invalid value{Style.RESET_ALL}")
                    
            elif choice == "4":
                keywords = input("Name must contain (comma-separated): ").split(",")
                keywords = [k.strip() for k in keywords if k.strip()]
                if keywords:
                    self.config.filters["name_contains"] = keywords
                    print(f"{Fore.GREEN}✓ Filter added{Style.RESET_ALL}")
                    
            elif choice == "5":
                keywords = input("Name must NOT contain (comma-separated): ").split(",")
                keywords = [k.strip() for k in keywords if k.strip()]
                if keywords:
                    self.config.filters["name_excludes"] = keywords
                    print(f"{Fore.GREEN}✓ Filter added{Style.RESET_ALL}")
                    
            elif choice == "6":
                keywords = input("Symbol must contain (comma-separated): ").split(",")
                keywords = [k.strip() for k in keywords if k.strip()]
                if keywords:
                    self.config.filters["symbol_contains"] = keywords
                    print(f"{Fore.GREEN}✓ Filter added{Style.RESET_ALL}")
                    
            elif choice == "7":
                keywords = input("Symbol must NOT contain (comma-separated): ").split(",")
                keywords = [k.strip() for k in keywords if k.strip()]
                if keywords:
                    self.config.filters["symbol_excludes"] = keywords
                    print(f"{Fore.GREEN}✓ Filter added{Style.RESET_ALL}")
                    
            elif choice == "8":
                self.config.filters = {}
                print(f"{Fore.GREEN}✓ All filters cleared{Style.RESET_ALL}")
                
            elif choice == "9":
                break
                
            if choice in ["1", "2", "3", "4", "5", "6", "7", "8"]:
                input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
    
    def manage_wallets_menu(self):
        """Manage wallet configurations"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{Fore.CYAN}Wallet Management{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
            
            if not self.wallets:
                print("No wallets configured")
            else:
                for i, wallet in enumerate(self.wallets, 1):
                    default = " (DEFAULT)" if wallet.is_default else ""
                    print(f"{i}. {wallet.label or 'Unnamed'}{default}")
                    print(f"   Address: {wallet.address[:8]}...{wallet.address[-6:]}")
                    has_key = "Yes" if wallet.private_key else "No"
                    print(f"   Private Key: {has_key}")
            
            print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
            print("1. Add Wallet")
            print("2. Remove Wallet")
            print("3. Set Default Wallet")
            print("4. Test Wallet Connection")
            print("5. Back to Main Menu")
            
            choice = input(f"\n{Fore.CYAN}Select option: {Style.RESET_ALL}")
            
            if choice == "1":
                label = input("Wallet label: ")
                address = input("Wallet address (public key): ")
                print(f"{Fore.YELLOW}Private key is required for auto-trading{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Supported formats:{Style.RESET_ALL}")
                print(f"  • Base58 encoded (e.g., 5JuE...)")
                print(f"  • Hexadecimal (e.g., a1b2c3...)")
                print(f"  • JSON array (e.g., [128,32,15...])")
                print(f"  • Comma-separated (e.g., 128,32,15...)")
                private_key = input("Private key: ")
                
                wallet = WalletConfig(
                    address=address,
                    private_key=private_key,
                    label=label,
                    is_default=len(self.wallets) == 0
                )
                self.wallets.append(wallet)
                print(f"{Fore.GREEN}✓ Wallet added{Style.RESET_ALL}")
                
            elif choice == "2" and self.wallets:
                try:
                    idx = int(input("Wallet number to remove: ")) - 1
                    if 0 <= idx < len(self.wallets):
                        self.wallets.pop(idx)
                        print(f"{Fore.GREEN}✓ Wallet removed{Style.RESET_ALL}")
                except (ValueError, IndexError):
                    print(f"{Fore.RED}Invalid selection{Style.RESET_ALL}")
                    
            elif choice == "3" and self.wallets:
                try:
                    idx = int(input("Wallet number to set as default: ")) - 1
                    if 0 <= idx < len(self.wallets):
                        for w in self.wallets:
                            w.is_default = False
                        self.wallets[idx].is_default = True
                        print(f"{Fore.GREEN}✓ Default wallet set{Style.RESET_ALL}")
                except (ValueError, IndexError):
                    print(f"{Fore.RED}Invalid selection{Style.RESET_ALL}")
                    
            elif choice == "4" and self.wallets:
                try:
                    idx = int(input("Wallet number to test: ")) - 1
                    if 0 <= idx < len(self.wallets):
                        wallet = self.wallets[idx]
                        if wallet.private_key:
                            keypair = self.parse_private_key(wallet.private_key)
                            if keypair:
                                pubkey = str(keypair.pubkey())
                                print(f"{Fore.GREEN}✓ Private key valid!{Style.RESET_ALL}")
                                print(f"   Public key: {pubkey}")
                                if pubkey != wallet.address and wallet.address:
                                    print(f"{Fore.YELLOW}⚠ Warning: Derived public key doesn't match stored address{Style.RESET_ALL}")
                            else:
                                print(f"{Fore.RED}✗ Invalid private key format{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.YELLOW}No private key configured{Style.RESET_ALL}")
                except (ValueError, IndexError):
                    print(f"{Fore.RED}Invalid selection{Style.RESET_ALL}")
                    
            elif choice == "5":
                break
                
            if choice in ["1", "2", "3", "4"]:
                input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
    
    def trading_settings_menu(self):
        """Configure trading settings"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{Fore.CYAN}Trading Settings{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
            
            print(f"Auto-buy: {self.config.auto_buy}")
            print(f"Buy amount: {self.config.buy_amount_sol} SOL")
            print(f"Slippage: {'auto' if self.config.use_auto_slippage else str(self.config.slippage) + '%'}")
            print(f"Priority fee: {'auto' if self.config.use_auto_priority else str(self.config.priority_fee) + ' SOL'}")
            if self.config.use_auto_priority:
                print(f"Priority level: {self.config.priority_fee_level}")
            print(f"Max retries: {self.config.max_retries}")
            print(f"Take profit: {self.config.take_profit}%")
            print(f"Stop loss: {self.config.stop_loss}%")
            
            print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
            print("1. Toggle Auto-buy")
            print("2. Set Buy Amount (SOL)")
            print("3. Configure Slippage")
            print("4. Configure Priority Fee")
            print("5. Set Take Profit %")
            print("6. Set Stop Loss %")
            print("7. Back to Main Menu")
            
            choice = input(f"\n{Fore.CYAN}Select option: {Style.RESET_ALL}")
            
            if choice == "1":
                self.config.auto_buy = not self.config.auto_buy
                status = "enabled" if self.config.auto_buy else "disabled"
                print(f"{Fore.GREEN}✓ Auto-buy {status}{Style.RESET_ALL}")
                
            elif choice == "2":
                try:
                    amount = float(input("Buy amount (SOL): "))
                    if amount > 0:
                        self.config.buy_amount_sol = amount
                        print(f"{Fore.GREEN}✓ Buy amount updated{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}Invalid amount{Style.RESET_ALL}")
                    
            elif choice == "3":
                print("\n1. Use auto slippage (dynamic)")
                print("2. Set manual slippage")
                sub_choice = input("Select: ")
                if sub_choice == "1":
                    self.config.use_auto_slippage = True
                    print(f"{Fore.GREEN}✓ Auto slippage enabled{Style.RESET_ALL}")
                elif sub_choice == "2":
                    self.config.use_auto_slippage = False
                    try:
                        slippage = float(input("Slippage %: "))
                        if 0 <= slippage <= 100:
                            self.config.slippage = slippage
                            print(f"{Fore.GREEN}✓ Manual slippage set{Style.RESET_ALL}")
                    except ValueError:
                        print(f"{Fore.RED}Invalid value{Style.RESET_ALL}")
                    
            elif choice == "4":
                print("\n1. Use auto priority fee")
                print("2. Set manual priority fee")
                sub_choice = input("Select: ")
                if sub_choice == "1":
                    self.config.use_auto_priority = True
                    print("\nPriority levels: min, low, medium, high, veryHigh, unsafeMax")
                    level = input("Select level (default: medium): ").strip() or "medium"
                    if level in ["min", "low", "medium", "high", "veryHigh", "unsafeMax"]:
                        self.config.priority_fee_level = level
                        print(f"{Fore.GREEN}✓ Auto priority fee enabled ({level}){Style.RESET_ALL}")
                elif sub_choice == "2":
                    self.config.use_auto_priority = False
                    try:
                        fee = float(input("Priority fee (SOL): "))
                        if fee >= 0:
                            self.config.priority_fee = fee
                            print(f"{Fore.GREEN}✓ Manual priority fee set{Style.RESET_ALL}")
                    except ValueError:
                        print(f"{Fore.RED}Invalid value{Style.RESET_ALL}")
                    
            elif choice == "5":
                try:
                    tp = float(input("Take profit %: "))
                    if tp > 0:
                        self.config.take_profit = tp
                        print(f"{Fore.GREEN}✓ Take profit updated{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}Invalid value{Style.RESET_ALL}")
                    
            elif choice == "6":
                try:
                    sl = float(input("Stop loss %: "))
                    if sl > 0:
                        self.config.stop_loss = sl
                        print(f"{Fore.GREEN}✓ Stop loss updated{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}Invalid value{Style.RESET_ALL}")
                    
            elif choice == "7":
                break
                
            if choice in ["1", "2", "3", "4", "5", "6"]:
                input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
    
    def view_statistics(self):
        """Display statistics and positions"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\n{Fore.CYAN}Statistics & Positions{Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
        
        print(f"{Fore.YELLOW}Session Statistics:{Style.RESET_ALL}")
        print(f"  Tokens analyzed: {self.stats['tokens_analyzed']}")
        print(f"  Tokens matched: {self.stats['tokens_matched']}")
        print(f"  Trades executed: {self.stats['trades_executed']}")
        print(f"  Trades failed: {self.stats['trades_failed']}")
        print(f"  Total profit: {self.stats['profit_total']:.4f} SOL")
        
        if self.matched_tokens:
            print(f"\n{Fore.YELLOW}Recent Matches (Last 5):{Style.RESET_ALL}")
            for token in self.matched_tokens[-5:]:
                print(f"  • {token.get('symbol', 'Unknown')} - {token.get('name', 'Unknown')}")
                print(f"    MC: {token.get('marketCapSol', 0):.4f} SOL")
        
        if self.positions:
            print(f"\n{Fore.YELLOW}Open Positions:{Style.RESET_ALL}")
            for mint, pos in self.positions.items():
                status_color = Fore.GREEN if pos.get('status') == 'confirmed' else Fore.YELLOW
                print(f"\n  {Fore.CYAN}{pos['symbol']}{Style.RESET_ALL} - {pos['name']}")
                print(f"    Amount: {pos['amount_sol']} SOL")
                print(f"    Tokens: {pos.get('amount_tokens', 0):.2f}")
                print(f"    Entry MC: {pos['entry_price']:.4f} SOL")
                print(f"    Time: {pos['timestamp']}")
                if 'tx_hash' in pos:
                    print(f"    TX: {pos['tx_hash'][:16]}...{pos['tx_hash'][-16:]}")
                    print(f"    Status: {status_color}{pos.get('status', 'unknown')}{Style.RESET_ALL}")
                    print(f"    {Fore.BLUE}View: https://solscan.io/tx/{pos['tx_hash']}{Style.RESET_ALL}")
        
        input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
    
    def advanced_settings_menu(self):
        """Advanced settings menu"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"\n{Fore.CYAN}Advanced Settings{Style.RESET_ALL}")
            print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}\n")
            
            print(f"Max position size: {self.config.max_position_sol} SOL")
            print(f"Trail stop: {self.config.trail_stop}")
            print(f"Webhook URL: {'Set' if self.config.webhook_url else 'Not set'}")
            
            print(f"\n{Fore.YELLOW}Options:{Style.RESET_ALL}")
            print("1. Set Max Position Size")
            print("2. Toggle Trail Stop")
            print("3. Set Webhook URL")
            print("4. Export Configuration")
            print("5. Import Configuration")
            print("6. Back to Main Menu")
            
            choice = input(f"\n{Fore.CYAN}Select option: {Style.RESET_ALL}")
            
            if choice == "1":
                try:
                    size = float(input("Max position size (SOL): "))
                    if size > 0:
                        self.config.max_position_sol = size
                        print(f"{Fore.GREEN}✓ Max position size updated{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}Invalid value{Style.RESET_ALL}")
                    
            elif choice == "2":
                self.config.trail_stop = not self.config.trail_stop
                status = "enabled" if self.config.trail_stop else "disabled"
                print(f"{Fore.GREEN}✓ Trail stop {status}{Style.RESET_ALL}")
                
            elif choice == "3":
                url = input("Webhook URL (leave empty to clear): ").strip()
                self.config.webhook_url = url if url else None
                print(f"{Fore.GREEN}✓ Webhook URL updated{Style.RESET_ALL}")
                
            elif choice == "4":
                filename = input("Export filename: ").strip()
                if filename:
                    try:
                        with open(filename, 'w') as f:
                            export_data = {
                                "config": asdict(self.config),
                                "wallets": [asdict(w) for w in self.wallets],
                                "stats": self.stats
                            }
                            json.dump(export_data, f, indent=2)
                        print(f"{Fore.GREEN}✓ Configuration exported to {filename}{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"{Fore.RED}Export failed: {e}{Style.RESET_ALL}")
                        
            elif choice == "5":
                filename = input("Import filename: ").strip()
                if filename and os.path.exists(filename):
                    try:
                        with open(filename, 'r') as f:
                            import_data = json.load(f)
                            self.config = SniperConfig(**import_data["config"])
                            self.wallets = [WalletConfig(**w) for w in import_data["wallets"]]
                            if "stats" in import_data:
                                self.stats = import_data["stats"]
                        print(f"{Fore.GREEN}✓ Configuration imported{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"{Fore.RED}Import failed: {e}{Style.RESET_ALL}")
                        
            elif choice == "6":
                break
                
            if choice in ["1", "2", "3", "4", "5"]:
                input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
    
    async def run(self):
        """Main application loop"""
        await self.initialize()
        
        while True:
            self.display_main_menu()
            choice = input(f"\n{Fore.CYAN}Select option: {Style.RESET_ALL}")
            
            if choice == "1":
                # Start monitoring
                if not self.wallets and self.config.auto_buy:
                    print(f"{Fore.RED}Please configure a wallet first!{Style.RESET_ALL}")
                    input(f"{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.YELLOW}Starting monitor... Press Ctrl+C to stop{Style.RESET_ALL}")
                    try:
                        await self.monitor_tokens()
                    except KeyboardInterrupt:
                        print(f"\n{Fore.YELLOW}Monitor stopped by user{Style.RESET_ALL}")
                        self.running = False
                    input(f"{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
                    
            elif choice == "2":
                self.configure_filters_menu()
                
            elif choice == "3":
                self.manage_wallets_menu()
                
            elif choice == "4":
                self.trading_settings_menu()
                
            elif choice == "5":
                self.view_statistics()
                
            elif choice == "6":
                self.advanced_settings_menu()
                
            elif choice == "7":
                self.api_settings_menu()
                
            elif choice == "8":
                await self.save_config()
                input(f"{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")
                
            elif choice == "9":
                print(f"\n{Fore.YELLOW}Saving configuration...{Style.RESET_ALL}")
                await self.save_config()
                print(f"{Fore.GREEN}Goodbye!{Style.RESET_ALL}")
                break
            
            else:
                print(f"{Fore.RED}Invalid option{Style.RESET_ALL}")
                input(f"{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")

async def main():
    """Main entry point"""
    print(f"{Fore.CYAN}Initializing Augmentry Tools - Sniper Bot...{Style.RESET_ALL}")
    sniper = TokenSniper()
    await sniper.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Application terminated by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)