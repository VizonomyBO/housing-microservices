"""
Application entry point for the Account Service.
"""
import os
from app import create_app, db
from app.models import User, RefreshToken  # Import models so SQLAlchemy knows about them

app = create_app()

if __name__ == '__main__':
    # Create database tables if they don't exist
    with app.app_context():
        try:
            # Import models to ensure they're registered with SQLAlchemy
            # This ensures db.create_all() knows about all models
            
            # Only drop tables if explicitly requested via environment variable
            # This is safe for development but should be replaced with migrations in production
            if os.getenv('RESET_DB', 'false').lower() == 'true':
                db.drop_all()
                print("Dropped all existing tables")
            
            db.create_all()
            print("Database tables created successfully")
        except Exception as e:
            print(f"Error creating database tables: {e}")
            import traceback
            traceback.print_exc()
    
    # Run the application
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

