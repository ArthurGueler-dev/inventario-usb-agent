# tests/test_hasher.py
import hashlib
import pytest
from agent.hasher import is_stable_serial, compute_hash_id


class TestIsStableSerial:
    def test_none_is_unstable(self):
        assert is_stable_serial(None) is False

    def test_empty_is_unstable(self):
        assert is_stable_serial('') is False
        assert is_stable_serial('   ') is False

    def test_windows_generated_unstable(self):
        # padrão \d&[A-F0-9]{8}
        assert is_stable_serial('3&11583659&0') is False
        assert is_stable_serial('1&ABCDEF12&0') is False

    def test_factory_serial_stable(self):
        assert is_stable_serial('1234567890') is True
        assert is_stable_serial('ABCD1234') is True
        assert is_stable_serial('AA00BB11CC22') is True

    def test_logitech_receiver_unstable(self):
        # serial típico do Unifying Receiver
        assert is_stable_serial('3&11583659&0') is False


class TestComputeHashId:
    def test_stable_serial_includes_serial(self):
        hash_id, stable = compute_hash_id('046D', 'C52B', 'ABCDEF1234')
        assert stable is True
        expected = hashlib.sha256('046D:C52B:ABCDEF1234'.encode()).hexdigest()
        assert hash_id == expected

    def test_unstable_serial_excluded(self):
        hash_id, stable = compute_hash_id('046D', 'C52B', '3&11583659&0')
        assert stable is False
        expected = hashlib.sha256('046D:C52B'.encode()).hexdigest()
        assert hash_id == expected

    def test_none_serial(self):
        hash_id, stable = compute_hash_id('045E', '082F', None)
        assert stable is False
        expected = hashlib.sha256('045E:082F'.encode()).hexdigest()
        assert hash_id == expected

    def test_vid_pid_normalized_to_uppercase_zfill(self):
        hash_id_lower, _ = compute_hash_id('46d', 'c52b', None)
        hash_id_upper, _ = compute_hash_id('046D', 'C52B', None)
        assert hash_id_lower == hash_id_upper

    def test_short_vid_zero_padded(self):
        hash_id, _ = compute_hash_id('F', '1', None)
        expected = hashlib.sha256('000F:0001'.encode()).hexdigest()
        assert hash_id == expected

    def test_returns_64_char_hex(self):
        hash_id, _ = compute_hash_id('046D', 'C52B', None)
        assert len(hash_id) == 64
        assert all(c in '0123456789abcdef' for c in hash_id)

    def test_different_serials_different_hashes(self):
        h1, _ = compute_hash_id('046D', 'C52B', 'SERIAL001')
        h2, _ = compute_hash_id('046D', 'C52B', 'SERIAL002')
        assert h1 != h2

    def test_serial_case_insensitive(self):
        h1, _ = compute_hash_id('046D', 'C52B', 'abcdef')
        h2, _ = compute_hash_id('046D', 'C52B', 'ABCDEF')
        assert h1 == h2
