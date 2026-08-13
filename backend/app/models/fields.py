"""
SQLAlchemy 加密字段类型

提供 EncryptedString 类型装饰器，在 ORM 层透明加解密。
应用层读写明文字符串，数据库持久化 base64 密文。

用法:
    from app.models.fields import EncryptedString

    class MyModel(Base):
        __tablename__ = "my_table"
        ...
        secret_field: Mapped[str] = mapped_column(EncryptedString, nullable=True)
"""
from sqlalchemy.types import TypeDecorator, Text


class EncryptedString(TypeDecorator):
    """
    AES-256-GCM 加密字符串字段类型。

    - 数据库存储: Text (base64 密文，含 nonce + ciphertext + tag)
    - Python 读写: str (明文)
    - 透明加解密: process_bind_param (写) / process_result_value (读)
    - NULL 安全: None 透传不加密

    注意事项:
        - 每次加密使用随机 nonce，同一明文产生不同密文
        - 不可直接对密文列做 WHERE / LIKE / ORDER BY 查询
        - 如需可查询的加密字段，请在应用层维护 HMAC 索引列
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        """写入数据库前加密"""
        if value is None:
            return None
        from app.core.encryption import encrypt
        return encrypt(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        """从数据库读出后解密"""
        if value is None:
            return None
        from app.core.encryption import decrypt
        return decrypt(value)
