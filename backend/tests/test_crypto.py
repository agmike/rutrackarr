import stat

from cryptography.fernet import Fernet

from rutrackarr.crypto import KEY_FILE, SecretBox


def test_generated_key_file_is_private_and_reused(tmp_path):
    box = SecretBox.from_settings(None, tmp_path)
    token = box.encrypt("hunter2")
    mode = stat.S_IMODE((tmp_path / KEY_FILE).stat().st_mode)
    assert mode == 0o600
    assert SecretBox.from_settings(None, tmp_path).decrypt(token) == "hunter2"


def test_env_key_and_wrong_key(tmp_path):
    key = Fernet.generate_key().decode()
    token = SecretBox.from_settings(key, tmp_path).encrypt("x")
    assert not (tmp_path / KEY_FILE).exists()
    assert SecretBox.from_settings(Fernet.generate_key().decode(), tmp_path).decrypt(token) is None
