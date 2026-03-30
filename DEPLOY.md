# Chișinău Routing Engine - Deploy to Render

## 🚀 Quick Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Helloguys3324/-ChisinauRouting)

## Manual Setup

### 1. Create Render Account
Go to https://render.com and sign up with GitHub

### 2. Create New Web Service
1. Click **New +** → **Web Service**
2. Connect your GitHub repository: `Helloguys3324/-ChisinauRouting`
3. Configure:
   - **Name:** `chisinau-routing`
   - **Region:** Frankfurt (EU)
   - **Branch:** `main`
   - **Root Directory:** `webapp`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --worker-class eventlet -w 1 app:app`

### 3. Environment Variables
Add these in Render dashboard → **Environment**:

| Variable | Value |
|----------|-------|
| `PYTHON_VERSION` | `3.11.0` |
| `TOMTOM_API_KEY` | Your TomTom API key (get free at https://developer.tomtom.com/) |
| `SECRET_KEY` | Any random string |

### 4. Deploy
Click **Create Web Service** and wait ~2-3 minutes for deployment.

Your app will be available at: `https://chisinau-routing.onrender.com`

## 📁 Files Structure

```
webapp/
├── app.py              # Flask application
├── algorithms.py       # Kruskal, Dijkstra, A* algorithms
├── requirements.txt    # Python dependencies
├── Procfile           # Render/Heroku config
├── templates/
│   └── index.html     # Map interface
└── .env.example       # Environment template
```

## 🔐 Security

- API keys are stored in environment variables (never in code)
- `.env` files are in `.gitignore`
- Use `.env.example` as template

## 🛠 Local Development

```bash
cd webapp
cp .env.example .env
# Edit .env with your API keys
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```
