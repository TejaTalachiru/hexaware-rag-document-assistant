#!/usr/bin/env python3
import requests
import time
import sys

def check_elasticsearch():
    """Check if Elasticsearch is running with auth"""
    try:
        # Use the credentials from your setup
        response = requests.get(
            "https://localhost:9200",
            auth=("elastic", "NIC-W*Z0nK-t9xs*VBsc"),
            verify=False,  # Skip SSL verification for local dev
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Elasticsearch check failed: {e}")
        return False

def check_ollama():
    """Check if Ollama is running"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Ollama check failed: {e}")
        return False

def check_llama3_model():
    """Check if Llama3 model is available"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return any("llama3" in model.get("name", "") for model in models)
    except:
        pass
    return False

def main():
    print("🎯 RAG System - Simple Startup Check")
    print("=" * 40)
    
    # Check Elasticsearch
    print("1️⃣ Checking Elasticsearch...")
    if check_elasticsearch():
        print("✅ Elasticsearch is running and authenticated")
    else:
        print("❌ Elasticsearch check failed. Make sure it's running with the correct password.")
        print("💡 Your Elasticsearch password: NIC-W*Z0nK-t9xs*VBsc")
        sys.exit(1)
    
    # Check Ollama
    print("\n2️⃣ Checking Ollama...")
    if check_ollama():
        print("✅ Ollama is running")
    else:
        print("❌ Ollama not running. Start it with: ollama serve")
        sys.exit(1)
    
    # Check Llama3 model
    print("\n3️⃣ Checking Llama3 model...")
    if check_llama3_model():
        print("✅ Llama3 model is available")
    else:
        print("⏳ Llama3 model not found. Installing...")
        import subprocess
        try:
            subprocess.run(["ollama", "pull", "llama3"], check=True)
            print("✅ Llama3 model installed successfully")
        except subprocess.CalledProcessError:
            print("❌ Failed to install Llama3. Run manually: ollama pull llama3")
            sys.exit(1)
    
    print("\n🎉 All systems ready!")
    print("\n📋 Now run these commands in separate terminals:")
    print("1️⃣ Backend:  python -m src.api.main")
    print("2️⃣ Frontend: streamlit run src/ui/streamlit_app.py")
    print("\n🌐 Then open: http://localhost:8501")

if __name__ == "__main__":
    main()
