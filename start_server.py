import os
import sys

# Suppress TensorFlow warnings
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

# Suppress other warnings
import warnings
warnings.filterwarnings('ignore')

# Now run uvicorn
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["app/ui/*", "*.pyc", "__pycache__"],  # Exclude UI folder
        log_level="info"
    )