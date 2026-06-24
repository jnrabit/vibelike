"""
Verschlüsselung und Hashing für vibelike.

- XOR-basierte Verschlüsselung für sensitive Daten (wie API-Keys)
- SHA256-Hashing für persistierte Datenintegrität

XOR ist NICHT kryptographisch sicher — schützt nur vor casual inspection.
SHA256 ist kryptographisch sicher und stabil über Prozessneustarts.
"""

import os
import base64
import hashlib
from typing import Optional


def _get_master_key() -> str:
    """
    Hol den Master-Encryption-Key.
    
    Fallback-Strategie:
    1. VIBELIKE_ENCRYPTION_KEY Umgebungsvariable
    2. Hostname + statischer Seed (konsistent über Neustarts)
    3. Fallback: "vibelike_default_key" (NOT SECURE!)
    """
    # Versuche aus Umgebung
    if key := os.environ.get("VIBELIKE_ENCRYPTION_KEY"):
        return key
    
    # Fallback: Hostname + statischer Seed
    try:
        hostname = os.uname().nodename
        return f"{hostname}_vibelike_v1"
    except Exception:
        # Fallback fallback
        return "vibelike_default_key"


def xor_encrypt(plaintext: str, master_key: Optional[str] = None) -> str:
    """
    Verschlüssel einen String mit XOR.
    
    Args:
        plaintext: Zu verschlüsselnder String
        master_key: Optionaler Master-Key (default: _get_master_key())
    
    Returns:
        Base64-codierter verschlüsselter String
    """
    if master_key is None:
        master_key = _get_master_key()
    
    # Erweitere Key auf Länge von plaintext via SHA256-Kette
    key_bytes = master_key.encode('utf-8')
    plaintext_bytes = plaintext.encode('utf-8')
    
    # Generiere längeren Key durch wiederholtes Hashing
    extended_key = b''
    current = key_bytes
    while len(extended_key) < len(plaintext_bytes):
        current = hashlib.sha256(current).digest()
        extended_key += current
    
    # XOR
    ciphertext_bytes = bytes(a ^ b for a, b in zip(plaintext_bytes, extended_key[:len(plaintext_bytes)]))
    
    # Base64
    return base64.b64encode(ciphertext_bytes).decode('utf-8')


def xor_decrypt(ciphertext: str, master_key: Optional[str] = None) -> str:
    """
    Entschlüssel einen XOR-verschlüsselten String.
    
    Args:
        ciphertext: Base64-codierter verschlüsselter String
        master_key: Optionaler Master-Key (default: _get_master_key())
    
    Returns:
        Decrypted plaintext String
    """
    if master_key is None:
        master_key = _get_master_key()
    
    try:
        # Dekodiere Base64
        ciphertext_bytes = base64.b64decode(ciphertext.encode('utf-8'))
        
        # Generiere längeren Key (identisch zu Encryption)
        key_bytes = master_key.encode('utf-8')
        extended_key = b''
        current = key_bytes
        while len(extended_key) < len(ciphertext_bytes):
            current = hashlib.sha256(current).digest()
            extended_key += current
        
        # XOR (Inverse ist wieder XOR)
        plaintext_bytes = bytes(a ^ b for a, b in zip(ciphertext_bytes, extended_key[:len(ciphertext_bytes)]))
        
        return plaintext_bytes.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}")


def stable_hash_sha256(data: str, hex_length: Optional[int] = None) -> str:
    """
    Erzeuge einen stabilen SHA256-Hash für einen String.
    
    Im Gegensatz zu Pythons `hash()` ist dieser über Prozessneustarts stabil.
    
    Args:
        data: String zum Hashen
        hex_length: Optional: Länge des Hex-Strings (wird vom Anfang gekürzt)
                   default: 32 (voller SHA256)
    
    Returns:
        Hex-String des SHA256-Hashs (oder gekürzt)
    """
    h = hashlib.sha256(data.encode('utf-8')).hexdigest()
    if hex_length:
        return h[:hex_length]
    return h


def stable_hash_int(data: str, modulo: Optional[int] = None) -> int:
    """
    Erzeuge einen stabilen numerischen Hash für einen String.
    
    Args:
        data: String zum Hashen
        modulo: Optional: Modulo für Range-Begrenzung (z.B. 2**32)
    
    Returns:
        Integer-Hash (stabilisiert durch SHA256)
    """
    h = hashlib.sha256(data.encode('utf-8')).digest()
    # Konvertiere erste 8 Bytes zu Integer
    hash_int = int.from_bytes(h[:8], byteorder='big')
    if modulo:
        hash_int = hash_int % modulo
    return hash_int


def load_api_keys_from_env_file(env_file_path: Optional[str] = None) -> dict:
    """
    Lade verschlüsselte API-Keys aus ~/.vibeweb.env und entschlüssele sie.
    
    Args:
        env_file_path: Pfad zur .env-Datei (default: ~/.vibeweb.env)
    
    Returns:
        Dict mit entschlüsselten Keys {KEY_NAME: plaintext_value}
    """
    from pathlib import Path
    
    if env_file_path is None:
        env_file_path = Path.home() / ".vibeweb.env"
    else:
        env_file_path = Path(env_file_path)
    
    keys = {}
    
    if not env_file_path.exists():
        return keys
    
    try:
        import json
        content = env_file_path.read_text(encoding="utf-8").strip()
        
        if content.startswith("{"):
            # JSON-Format
            data = json.loads(content)
            for key_name, encrypted_value in data.items():
                try:
                    keys[key_name] = xor_decrypt(encrypted_value)
                except ValueError:
                    # Fallback: Falls nicht verschlüsselt (altes Format), nutze direkt
                    keys[key_name] = encrypted_value
        else:
            # Altes Format (KEY=value)
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    keys[k.strip()] = v.strip()
    except Exception as e:
        import warnings
        warnings.warn(f"Failed to load API keys from {env_file_path}: {e}")
    
    return keys
