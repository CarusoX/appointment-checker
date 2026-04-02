from cryptography.fernet import Fernet


def encrypt_password(raw_password: str, key: str) -> str:
    f = Fernet(key.encode())
    return f.encrypt(raw_password.encode()).decode()


def decrypt_password(encrypted: str, key: str) -> str:
    f = Fernet(key.encode())
    return f.decrypt(encrypted.encode()).decode()
