# Ubuntu Control Panel

An advanced web-based hosting control panel specifically designed for Ubuntu 24.04 LTS servers.

## Features

- **User Authentication System**: Secure login with role-based access (Admin, User) and optional 2FA
- **Inbuilt File Manager**: Upload, rename, move, delete, and edit files with a responsive interface
- **Integrated Terminal Support**: Web-based terminal with real-time access to Ubuntu shell
- **Python File Deployer**: Upload and run Python scripts with dependency management
- **Dashboard Overview**: Real-time system metrics with modern charts
- **Security Measures**: HTTPS support, IP whitelisting, and activity logs

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: React.js with TailwindCSS
- **Database**: MongoDB
- **Terminal**: xterm.js
- **Websockets**: For real-time updates

## Installation

### Prerequisites

- Ubuntu 24.04 LTS
- Python 3.10+
- Node.js 18+
- MongoDB

### Backend Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/ubuntu-control-panel.git
   cd ubuntu-control-panel
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create an `.env` file based on the example:
   ```bash
   cp .env.example .env
   ```

4. Edit the `.env` file to configure your settings.

5. Run the application:
   ```bash
   python run.py
   ```

### Frontend Setup

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Create an `.env` file:
   ```
   REACT_APP_API_URL=http://localhost:8000
   ```

3. Start the development server:
   ```bash
   npm start
   ```

## One-Line Deployment Script

For quick deployment on Ubuntu:

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/ubuntu-control-panel/main/deploy.sh | bash
```

## Security Considerations

- Change the default admin password immediately
- Use HTTPS in production
- Consider firewall rules to restrict access
- Keep the system updated regularly

## Development

### Running in Development Mode

```bash
# Backend
cd backend
python run.py

# Frontend
cd frontend
npm start
```

### Building for Production

```bash
# Frontend
cd frontend
npm run build

# Copy build files to backend static directory
cp -r build/* ../backend/static/
```

## License

This project is licensed under the MIT License - see the LICENSE file for details. 