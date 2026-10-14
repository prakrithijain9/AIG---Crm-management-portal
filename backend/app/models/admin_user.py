import re

from sqlalchemy import CheckConstraint, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

USERNAME_MAX_LENGTH = 150

# ASCII letters, digits and . _ @ - only. This rules out whitespace anywhere, control and
# invisible characters, and look-alike Unicode letters, and it means Python's str.lower()
# agrees with PostgreSQL's lower() for every allowed character (the uniqueness index uses
# lower()). The same character class is enforced by the username_valid_characters CHECK.
USERNAME_CHARACTERS = "A-Za-z0-9._@-"
_USERNAME_RE = re.compile(f"[{USERNAME_CHARACTERS}]{{1,{USERNAME_MAX_LENGTH}}}")


# Shape of a PHC-format password hash: $<algorithm>$<segment>$<segment>[$...], e.g.
# $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>. Deliberately algorithm-agnostic: it catches a
# plaintext or truncated value without tying the schema to Argon2's current parameters or
# version, so pwdlib can rehash (or change algorithm) without a migration. Requiring Argon2id
# for new hashes is the job of the code that creates them. Enforced by the
# password_hash_phc_format CHECK; keep the two in sync (no ':' allowed, SQLAlchemy reads it as a bind).
PASSWORD_HASH_PATTERN = r"^\$[a-z0-9-]{1,32}(\$[A-Za-z0-9+/=.,-]+){2,}$"
_PASSWORD_HASH_RE = re.compile(r"\$[a-z0-9-]{1,32}(?:\$[A-Za-z0-9+/=.,-]+){2,}")
# The password_hash column length; Argon2id hashes are about 100 characters.
PASSWORD_HASH_MAX_LENGTH = 255


def is_phc_hash_format(value: str) -> bool:
    """True if `value` is a PHC-format hash the database will accept (its CHECK and column length)."""
    return (
        isinstance(value, str)
        and len(value) <= PASSWORD_HASH_MAX_LENGTH
        and _PASSWORD_HASH_RE.fullmatch(value) is not None
    )


class InvalidUsername(ValueError):
    pass


def validate_username(value: str) -> str:
    """Return `value` unchanged if it is a valid username, else raise InvalidUsername.

    Nothing is stripped or rewritten: " admin" is rejected, not silently turned into "admin".
    Admin creation must call this before saving; login must call it before looking a user up
    and treat InvalidUsername as an ordinary failed sign-in. The error message never echoes
    the value, which could be a password typed into the wrong field.
    """
    if not isinstance(value, str) or not _USERNAME_RE.fullmatch(value):
        raise InvalidUsername(
            f"Username must be 1-{USERNAME_MAX_LENGTH} characters, using only letters, digits, '.', '_', '@' or '-'."
        )
    return value


def username_lookup_key(value: str) -> str:
    """The validated username in lower case, for matching against lower(username)."""
    return validate_username(value).lower()


class AdminUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person who can sign in to the CRM. Only an Argon2id hash of the password is stored."""

    __tablename__ = "admin_users"
    # PostgreSQL tests CHECK constraints in alphabetical order by name, so a blank or padded
    # username reports the specific rule before the general username_valid_characters one.
    __table_args__ = (
        CheckConstraint("btrim(username) <> ''", name="username_not_blank"),
        # No leading/trailing spaces, so "admin" and "admin " cannot both look valid.
        CheckConstraint("username = btrim(username)", name="username_trimmed"),
        CheckConstraint(f"username ~ '^[{USERNAME_CHARACTERS}]+$'", name="username_valid_characters"),
        CheckConstraint("password_hash <> ''", name="password_hash_not_blank"),
        CheckConstraint(f"password_hash ~ '{PASSWORD_HASH_PATTERN}'", name="password_hash_phc_format"),
        CheckConstraint("token_version >= 0", name="token_version_non_negative"),
    )

    username: Mapped[str] = mapped_column(String(USERNAME_MAX_LENGTH))
    # PHC-format hash string (Argon2id is about 100 characters); room for stronger parameters.
    password_hash: Mapped[str] = mapped_column(String(PASSWORD_HASH_MAX_LENGTH))
    # An inactive admin cannot sign in, and their existing sessions stop working.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Copied into every session token; incrementing it revokes all of that admin's sessions.
    token_version: Mapped[int] = mapped_column(default=0, server_default=text("0"))

    def __repr__(self) -> str:
        # Never include password_hash.
        return f"AdminUser(id={self.id!r}, username={self.username!r}, is_active={self.is_active!r})"


# Usernames are unique regardless of case ("Admin" == "admin").
Index("uq_admin_users_username_lower", func.lower(AdminUser.username), unique=True)

# Safe, user-facing messages for admin_users constraint violations (see app.db.errors).
# They name the rule, never the submitted values.
ADMIN_USER_CONSTRAINT_MESSAGES = {
    "uq_admin_users_username_lower": "An admin with this username already exists.",
    "ck_admin_users_username_not_blank": "Username cannot be blank.",
    "ck_admin_users_username_trimmed": "Username cannot start or end with spaces.",
    "ck_admin_users_username_valid_characters": "Username contains characters that are not allowed.",
    "ck_admin_users_password_hash_not_blank": "Password hash is missing.",
    "ck_admin_users_password_hash_phc_format": "Password hash is not in the expected format.",
    "ck_admin_users_token_version_non_negative": "Token version cannot be negative.",
}
ADMIN_USER_SAVE_FAILED = "The admin account could not be saved."
