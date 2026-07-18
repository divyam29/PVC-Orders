from pvc_app import create_app

# Flask app factory entry point
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
