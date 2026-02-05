
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Downloading Spacy German Model (de_core_news_lg)..."
python -m spacy download de_core_news_sm

echo "Setup complete! Run the server with:"
echo "cd python && uvicorn main:app --reload"
