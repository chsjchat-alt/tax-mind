"""
字段级 AES-256-GCM 加解密工具

特性：
  - AES-256-GCM 认证加密（防篡改）
  - 每次加密生成随机 12 字节 nonce，同一明文产生不同密文
  - 密文格式: base64(nonce + ciphertext + tag)，16 + tag=16
  - 统一异常类型 EncryptionError，调用方无需处理底层细节

用法:
    from app.core.encryption import encrypt, decrypt

    ciphertext = encrypt("敏感数据")       # str → str (base64)
    plaintext  = decrypt(ciphertext)       # str → str
"""
import os
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

NONCE_BYTES = 12  # GCM 推荐 nonce 长度


class EncryptionError(Exception):
    """加解密异常（密钥错误、密文损坏等）"""


def _get_key() -> bytes:
    """从配置获取 32 字节 AES-256 密钥"""
    key_str = get_settings().encryption_key
    key = base64.b64decode(key_str)
    if len(key) != 32:
        raise EncryptionError(f"encryption_key must be 32 bytes, got {len(key)}")
    return key


def encrypt(plaintext: str) -> str:
    """
    使用 AES-256-GCM 加密明文字符串。

    Args:
        plaintext: 明文 (UTF-8 字符串)

    Returns:
        base64 编码的密文（包含 nonce + ciphertext + tag）

    Raises:
        EncryptionError: 加密失败
    """
    try:
        key = _get_key()
        nonce = os.urandom(NONCE_BYTES)
        aesgcm = AESGCM(key)
        data = plaintext.encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, data, None)
        # ciphertext 已包含 16 字节 tag，格式: nonce(12) + ct+tag
        return base64.b64encode(nonce + ciphertext).decode("ascii")
    except EncryptionError:
        raise
    except Exception as e:
        raise EncryptionError(f"Encryption failed: {e}") from e


def decrypt(ciphertext_b64: str) -> str:
    """
    使用 AES-256-GCM 解密密文。

    Args:
        ciphertext_b64: encrypt() 返回的 base64 密文

    Returns:
        解密后的明文 (UTF-8 字符串)

    Raises:
        EncryptionError: 解密失败（密钥不匹配、密文损坏、数据被篡改）
    """
    try:
        key = _get_key()
        raw = base64.b64decode(ciphertext_b64)
        if len(raw) <= NONCE_BYTES + 16:
            raise EncryptionError("Ciphertext too short, possibly corrupted")
        nonce = raw[:NONCE_BYTES]
        ciphertext = raw[NONCE_BYTES:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except EncryptionError:
        raise
    except Exception as e:
        raise EncryptionError(f"Decryption failed: {e}") from e
