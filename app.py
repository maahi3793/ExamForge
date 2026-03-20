import os
from flask import Flask
from backend.config import get_config
from backend.database import init_db
from backend.routes import main

def create_app():
    """Create and configure Flask application."""
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )

    config = get_config()
    app.secret_key = config['secret_key']

    # Initialize database
    init_db()

    # Register routes
    app.register_blueprint(main)

    return app


# Create the global app instance for WSGI deployment (Gunicorn)
app = create_app()

if __name__ == '__main__':
    print("\n🎓 ExamForge is running!")
    print("📍 Open: http://localhost:5000")
    print("🔑 Make sure your Gemini API key is set in .env\n")
    app.run(debug=True, port=5000)
