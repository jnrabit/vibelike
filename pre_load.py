def pre_load_all_models():
    """
    Trigger schwere Model-Imports beim Serverstart (damit Ollama warm lädt).

    CodeRetriever wird NICHT hier instantiiert — das passiert später in terminal.py:1502
    Dort wird die erste (und einzige) Instanz erstellt und über den Request-Cycle
    wiederverwendet. Pre-Load nur die Ollama-Modelle.
    """
    print("--- Starting pre-loading of models ---")

    # Ollama Qwen-Modell warmhalten (keep_alive=-1s = unbegrenzt)
    try:
        from terminal import QwenCoder, MODEL
        print(f"[PRE-LOAD] Warming up Ollama model: {MODEL}...")
        qwen = QwenCoder(model=MODEL)
        # Dummy-Call um das Modell zu laden
        qwen.generate(prompt="warmup", keep_alive="-1s")
        del qwen  # Explizit freigeben (aber Ollama hält es warm)
        print(f"[PRE-LOAD] Ollama {MODEL} warmed up.")
    except Exception as e:
        print(f"[WARN] Failed to warm up Qwen: {e}")

    print("--- Pre-loading complete ---")
