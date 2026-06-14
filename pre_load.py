from terminal import CodeRetriever, QwenCoder, MODEL

def pre_load_all_models():
    """
    Lädt alle schweren Modelle einmal beim Serverstart in den Speicher.
    """
    print("--- Starting unified pre-loading of all models ---")
    
    # 1. Lade Sentence-Transformer und Vaults
    try:
        print("[PRE-LOAD] Initializing CodeRetriever (Sentence Transformers)...")
        CodeRetriever(remote_url=None)
        print("[PRE-LOAD] CodeRetriever loaded successfully.")
    except Exception as e:
        print(f"[ERR] Failed to pre-load CodeRetriever: {e}")

    # 2. Lade Qwen-Modell in Ollama
    try:
        print(f"[PRE-LOAD] Pre-loading Ollama model: {MODEL}...")
        qwen_coder = QwenCoder(model=MODEL)
        # Sende eine leere Anfrage mit langer Keep-Alive-Zeit (-1s für unbegrenzt)
        qwen_coder.generate(prompt="", keep_alive="-1s")
        print(f"[PRE-LOAD] Ollama model {MODEL} loaded.")
    except Exception as e:
        print(f"[ERR] Failed to pre-load Qwen model: {e}")
    
    print("--- Unified pre-loading complete ---")
