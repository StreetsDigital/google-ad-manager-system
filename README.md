# Google Ad Manager Autonomous System

An autonomous system for managing Google Ad Manager operations, including inventory management, campaign operations, and reporting.

## Features

- MCP Server with FastAPI and SOAP client integration
- OAuth2 authentication flow
- Inventory management (ad units, placements, targeting)
- Campaign operations (orders, line items, creatives)
- Reporting infrastructure
- Advanced features and optimizations
- STDIO interface for command-line operations

## Prerequisites

- Python 3.8+
- Redis
- Google Ad Manager API access

## Setup

1. Clone the repository:
```bash
git clone https://github.com/streetsdigital/google-ad-manager-system.git
cd google-ad-manager-system
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate
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

## Usage

### HTTP Server

Run the HTTP server:
```bash
uvicorn src.main:app --reload
```

### STDIO Interface

The system provides a STDIO interface for command-line operations. This allows you to interact with the server using standard input/output streams.

#### Running the STDIO Server

```bash
python -m src.run_stdio_server
```

#### Making Requests

The STDIO interface accepts JSON-encoded requests with the following format:
```json
{
    "method": "GET|POST|PUT|DELETE",
    "path": "/endpoint/path",
    "body": {
        "optional": "request body"
    }
}
```

Responses are returned in this format:
```json
{
    "status": 200,
    "headers": {
        "content-type": "application/json"
    },
    "body": {
        "response": "data"
    }
}
```

#### Example Operations

1. Health Check:
```bash
echo '{"method": "GET", "path": "/health"}' | python -m src.run_stdio_server
```

2. Authentication:
```bash
echo '{
    "method": "POST",
    "path": "/auth/token",
    "body": {
        "client_id": "your_client_id",
        "client_secret": "your_client_secret"
    }
}' | python -m src.run_stdio_server
```

3. Create Campaign:
```bash
echo '{
    "method": "POST",
    "path": "/campaigns",
    "body": {
        "name": "Test Campaign",
        "advertiserId": "12345",
        "startDate": "2024-03-20",
        "endDate": "2024-04-20"
    }
}' | python -m src.run_stdio_server
```

4. Get Report:
```bash
echo '{
    "method": "GET",
    "path": "/reports/campaign-performance",
    "body": {
        "campaignId": "67890",
        "dateRange": "LAST_7_DAYS"
    }
}' | python -m src.run_stdio_server
```

#### Using the Helper Script

For convenience, you can use the provided helper script:

```bash
./scripts/mcp-cli.sh health  # Health check
./scripts/mcp-cli.sh auth    # Authentication
./scripts/mcp-cli.sh create-campaign '{"name": "Test"}' # Create campaign
```

## API Documentation

Visit `/docs` or `/redoc` when running the HTTP server for complete API documentation.

## Testing

Run the test suite:
```bash
pytest
```

Run specific test categories:
```bash
pytest src/tests/test_auth      # Auth tests
pytest src/tests/test_campaigns # Campaign tests
pytest src/tests/test_mcp      # MCP server tests
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
