"""OAuth2 setup utility for Google Ad Manager."""
import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

# OAuth2 scopes required for Google Ad Manager API
SCOPES = [
    'https://www.googleapis.com/auth/dfp'
]

def setup_oauth_flow(client_config_path: str, token_path: str = 'token.json') -> Credentials:
    """
    Set up OAuth2 flow and get credentials.
    
    Args:
        client_config_path: Path to client configuration JSON file
        token_path: Path to save/load token
        
    Returns:
        Credentials object
    """
    credentials = None
    
    # Load existing token if available
    if os.path.exists(token_path):
        with open(token_path, 'r') as token_file:
            token_data = json.load(token_file)
            credentials = Credentials.from_authorized_user_info(token_data, SCOPES)
    
    # If no valid credentials, run the OAuth flow
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(
                client_config=json.load(open(client_config_path)),
                scopes=SCOPES
            )
            credentials = flow.run_local_server(port=0)
            
            # Save the credentials
            with open(token_path, 'w') as token_file:
                token_file.write(credentials.to_json())
    
    return credentials

def main():
    """Main entry point for OAuth setup."""
    import argparse
    parser = argparse.ArgumentParser(description='Set up OAuth2 for Google Ad Manager')
    parser.add_argument('--config', required=True, help='Path to client configuration JSON file')
    parser.add_argument('--output', default='token.json', help='Path to save token')
    args = parser.parse_args()
    
    print("Starting OAuth2 setup...")
    credentials = setup_oauth_flow(args.config, args.output)
    print(f"Successfully obtained credentials!")
    print(f"Refresh token: {credentials.refresh_token}")
    print(f"Token saved to: {args.output}")
    
    # Print environment variable export commands
    print("\nAdd these to your environment:")
    print(f"export GAM_CLIENT_ID='{json.load(open(args.config))['web']['client_id']}'")
    print(f"export GAM_CLIENT_SECRET='{json.load(open(args.config))['web']['client_secret']}'")
    print(f"export GAM_REFRESH_TOKEN='{credentials.refresh_token}'")
    print("export GAM_APPLICATION_NAME='MCP_Test'")
    print("# Add your network code:")
    print("export GAM_NETWORK_CODE='YOUR_NETWORK_CODE'")

if __name__ == '__main__':
    main() 