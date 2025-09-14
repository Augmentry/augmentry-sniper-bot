# 🚀 Augmentry Sniper Bot

An advanced token sniping bot for Solana blockchain, integrated with Augmentry's trading infrastructure for automated token discovery and trading.


![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Solana](https://img.shields.io/badge/Solana-Mainnet-purple.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ⚠️ Disclaimer

**USE AT YOUR OWN RISK**. This bot is for educational purposes only. Cryptocurrency trading carries substantial risk of loss. The developers are not responsible for any financial losses incurred through the use of this software.

## 📋 Features

- **Real-time Token Monitoring** - WebSocket connection to Augmentry's stream for instant new token detection
- **Advanced Filtering System** - Multiple customizable filters for precise token targeting
- **Automated Trading** - Instant execution via Augmentry Swap API
- **Smart Slippage Management** - Auto or manual slippage configuration
- **Priority Fee Optimization** - Dynamic or fixed priority fees for faster transactions
- **Multi-Wallet Support** - Manage multiple wallets with secure key storage
- **Position Tracking** - Monitor open positions and P&L
- **Webhook Notifications** - Real-time alerts for trades and matches
- **Session Statistics** - Track performance metrics and success rates

## 🛠️ Prerequisites

- Python 3.8 or higher
- Solana wallet with SOL for trading
- Basic understanding of DeFi and token trading

## 📦 Installation

1. **Clone the repository**
```bash
git clone https://github.com/augmentry/augmentry-sniper-bot.git
cd augmentry-sniper-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Run the bot**
```bash
python augmentry_sniper.py
```

## 📝 Requirements

Create a `requirements.txt` file:
```txt
asyncio
websockets>=12.0
aiohttp>=3.9.0
httpx>=0.25.0
solana>=0.30.0
solders>=0.18.0
base58>=2.1.0
colorama>=0.4.6
```

## 🔧 Configuration

The bot stores configuration in `~/.augmentry_sniper/`:
- `config.json` - Main configuration settings
- `wallets.json` - Encrypted wallet information

### Initial Setup

1. **Add Wallet** - Configure your Solana wallet (private key required for trading)
2. **Set Filters** - Define market cap, liquidity, and keyword filters
3. **Configure Trading** - Set buy amount, slippage, and priority fees
4. **Enable Monitoring** - Start the WebSocket stream to detect new tokens

## 🎯 Filter Options

| Filter Type | Description | Example |
|------------|-------------|---------|
| Min Market Cap | Minimum market cap in SOL | 10 SOL |
| Max Market Cap | Maximum market cap in SOL | 1000 SOL |
| Min Liquidity | Minimum liquidity in bonding curve | 5 SOL |
| Name Contains | Keywords token name must contain | ["AI", "GPT"] |
| Name Excludes | Blacklisted words in token name | ["scam", "rug"] |
| Symbol Contains | Keywords symbol must contain | ["PEPE", "DOGE"] |
| Symbol Excludes | Blacklisted words in symbol | ["TEST", "FAKE"] |

## 💻 Usage

### Main Menu Options

1. **📊 Start Monitoring** - Begin scanning for new tokens
2. **⚙️ Configure Filters** - Set up token filtering rules
3. **👛 Manage Wallets** - Add/remove trading wallets
4. **💰 Trading Settings** - Configure buy amounts and fees
5. **📈 View Statistics** - Check performance and positions
6. **🔧 Advanced Settings** - Webhooks, position limits, etc.
7. **🔑 API Settings** - Configure custom API keys
8. **💾 Save Configuration** - Persist settings to disk

### Trading Parameters

- **Buy Amount**: Amount of SOL to spend per trade (default: 0.025 SOL)
- **Slippage**: Auto or manual percentage (default: 10%)
- **Priority Fee**: Transaction priority in SOL (default: 0.0005 SOL)
- **Max Retries**: Number of transaction retry attempts (default: 3)

## 🔐 Security

### Private Key Formats Supported

- Base58 encoded (e.g., `5JuE...`)
- Hexadecimal (e.g., `a1b2c3...`)
- JSON array (e.g., `[128,32,15...]`)
- Comma-separated (e.g., `128,32,15...`)

**⚠️ NEVER share your private keys. Store them securely!**

## 📊 API Endpoints

- **Swap API**: `https://swap-v2.augmentry.io`
- **Stream WebSocket**: `wss://stream.augmentry.io/api/data`
- **Data API**: `https://data.augmentry.io`

## 🚦 Status Indicators

- 🟢 **GREEN** - Successful operations
- 🟡 **YELLOW** - Warnings or pending operations
- 🔴 **RED** - Errors or failed operations
- 🔵 **BLUE** - Informational messages
- 🟣 **MAGENTA** - System boundaries

## 📈 Performance Tracking

The bot tracks:
- Tokens analyzed
- Tokens matched to filters
- Trades executed successfully
- Failed trade attempts
- Total profit/loss
- Open positions

## 🐛 Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**
   - Check internet connection
   - Verify API endpoints are accessible
   - Check if custom API key is required

2. **Transaction Failed**
   - Ensure wallet has sufficient SOL
   - Increase slippage tolerance
   - Raise priority fee for congested network

3. **Private Key Not Working**
   - Verify key format is supported
   - Check for extra spaces or characters
   - Ensure key matches wallet address

## 📝 Advanced Features

### Webhook Integration
Configure webhooks to receive notifications:
```json
{
  "event": "token_sniped",
  "token": {...},
  "trade": {...},
  "timestamp": "2024-01-01T00:00:00"
}
```

### Position Management
- **Take Profit**: Auto-sell at profit target (default: 50%)
- **Stop Loss**: Auto-sell at loss limit (default: 20%)
- **Trail Stop**: Dynamic stop-loss adjustment
- **Max Position**: Maximum SOL per position (default: 1.0 SOL)

## ⚡ Performance Tips

1. Use wired internet connection for lowest latency
2. Run on VPS close to Solana validators
3. Configure appropriate priority fees for network conditions
4. Use auto-slippage for dynamic market conditions
5. Set reasonable position limits to manage risk

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Augmentry team for API infrastructure
- Solana Foundation for blockchain technology
- Open source contributors

## 📞 Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Read the documentation thoroughly

## 🔄 Updates

Check for updates regularly:
```bash
git pull origin main
pip install -r requirements.txt --upgrade
```

---

**Remember**: Always DYOR (Do Your Own Research) and never invest more than you can afford to lose. Happy trading! 🚀