# Google Ad Manager Autonomous System

An autonomous system for managing Google Ad Manager operations, including inventory management, campaign operations, and reporting.

## Features

- MCP Server with FastAPI and SOAP client integration
- OAuth2 authentication flow
- Inventory management (ad units, placements, targeting)
- Campaign operations (orders, line items, creatives)
- Reporting infrastructure
- Advanced features and optimizations

## Prerequisites

- Python 3.8+
- Redis
- Google Ad Manager API access

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/google-ad-manager-system.git
cd google-ad-manager-system
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up Google Ad Manager API credentials:
   - Go to the [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project or select an existing one
   - Enable the Google Ad Manager API
   - Create OAuth 2.0 credentials (Web application type)
   - Download the client configuration file
   - Rename it to `client_config.json` and place it in the project root

5. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Update the values with your configuration:
     ```bash
     cp .env.example .env
     ```

6. Initialize the database and Redis:
   - Ensure Redis is running
   - Update Redis configuration in `.env` if needed

## Running the Application

1. Start the server:
```bash
python src/main.py
```

2. Access the API documentation:
   - OpenAPI UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Testing

Run the test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=src tests/
```

## Security Notes

1. Never commit sensitive credentials to version control:
   - Keep `.env` file local and never commit it
   - Use environment variables in production
   - Store secrets in a secure vault

2. Credential Management:
   - `client_config.json` is ignored by git
   - Use placeholder values in example files
   - Store production credentials securely

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.