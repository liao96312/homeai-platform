import base64
import hashlib
import hmac
import json
import struct
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from defusedxml import ElementTree as ET

from backend.app.core.config import settings


class WecomCryptoError(ValueError):
    pass


def verify_signature(token: str, signature: str, timestamp: str, nonce: str, encrypted: str) -> bool:
    if not token:
        raise WecomCryptoError("WECOM_CALLBACK_TOKEN is not configured")
    values = [token, timestamp, nonce, encrypted]
    raw = "".join(sorted(values))
    return hmac.compare_digest(hashlib.sha1(raw.encode("utf-8")).hexdigest(), signature)


def decrypt_wecom_message(encrypted: str) -> str:
    if not settings.wecom_encoding_aes_key:
        raise WecomCryptoError("WECOM_ENCODING_AES_KEY is not configured")
    aes_key = base64.b64decode(settings.wecom_encoding_aes_key + "=")
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16]))
    decryptor = cipher.decryptor()
    padded = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
    plain = remove_pkcs7_padding(padded)
    if len(plain) < 20:
        raise WecomCryptoError("Invalid decrypted message")
    msg_len = struct.unpack("!I", plain[16:20])[0]
    msg = plain[20 : 20 + msg_len]
    receive_id = plain[20 + msg_len :].decode("utf-8", errors="ignore")
    if settings.wecom_corp_id and receive_id != settings.wecom_corp_id:
        raise WecomCryptoError("Receive id does not match WECOM_CORP_ID")
    return msg.decode("utf-8")


def remove_pkcs7_padding(value: bytes) -> bytes:
    if not value:
        raise WecomCryptoError("Invalid PKCS7 padding")
    pad = value[-1]
    if pad < 1 or pad > 32:
        raise WecomCryptoError("Invalid PKCS7 padding")
    if len(value) < pad or value[-pad:] != bytes([pad]) * pad:
        raise WecomCryptoError("Invalid PKCS7 padding")
    return value[:-pad]


def extract_xml_text(xml_text: str, tag: str) -> str:
    root = ET.fromstring(xml_text)
    node = root.find(tag)
    return node.text if node is not None and node.text is not None else ""


def extract_encrypt_from_xml(xml_text: str) -> str:
    return extract_xml_text(xml_text, "Encrypt")


def parse_inbound_payload(body: bytes, content_type: str = "") -> dict[str, Any]:
    text = body.decode("utf-8", errors="ignore").strip()
    if not text:
        return {"msg_type": "empty", "content": "", "raw": {}}
    if "json" in content_type:
        raw = json.loads(text)
        return normalize_json_payload(raw)
    if text.startswith("{"):
        raw = json.loads(text)
        return normalize_json_payload(raw)
    return normalize_xml_payload(text)


def normalize_json_payload(raw: dict[str, Any]) -> dict[str, Any]:
    msg_type = raw.get("msgtype") or raw.get("MsgType") or "text"
    content = ""
    if msg_type == "text":
        text_obj = raw.get("text")
        if isinstance(text_obj, dict):
            content = text_obj.get("content", "")
        else:
            content = raw.get("Content") or raw.get("content") or ""
    else:
        content = raw.get("Content") or raw.get("content") or json.dumps(raw, ensure_ascii=False)
    return {
        "msg_type": msg_type,
        "from_user": raw.get("FromUserName") or raw.get("from_user") or raw.get("userid") or "",
        "content": content,
        "message_id": extract_message_id(raw),
        "raw": raw,
    }


def normalize_xml_payload(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    msg_type = get_child_text(root, "MsgType") or "text"
    content = get_child_text(root, "Content")
    return {
        "msg_type": msg_type,
        "from_user": get_child_text(root, "FromUserName"),
        "content": content,
        "message_id": get_child_text(root, "MsgId") or get_child_text(root, "MsgID"),
        "raw": {child.tag: child.text for child in root},
    }


def extract_message_id(raw: dict[str, Any]) -> str:
    for key in ("MsgId", "MsgID", "msgid", "msg_id", "message_id", "messageId"):
        value = raw.get(key)
        if value:
            return str(value)
    return ""


def get_child_text(root: Any, tag: str) -> str:
    node = root.find(tag)
    return node.text if node is not None and node.text else ""


def decrypt_callback_body(body: bytes, msg_signature: str, timestamp: str, nonce: str) -> str:
    xml_text = body.decode("utf-8", errors="ignore")
    encrypted = extract_encrypt_from_xml(xml_text)
    if not encrypted:
        return xml_text
    if not verify_signature(settings.wecom_callback_token, msg_signature, timestamp, nonce, encrypted):
        raise WecomCryptoError("Invalid msg_signature")
    return decrypt_wecom_message(encrypted)


def verify_url(echostr: str, msg_signature: str, timestamp: str, nonce: str) -> str:
    if not echostr:
        return "ok"
    if not settings.wecom_encoding_aes_key:
        raise WecomCryptoError("WECOM_ENCODING_AES_KEY is not configured")
    if not verify_signature(settings.wecom_callback_token, msg_signature, timestamp, nonce, echostr):
        raise WecomCryptoError("Invalid msg_signature")
    return decrypt_wecom_message(echostr)


def robot_webhook_url() -> str:
    if settings.wecom_robot_webhook_url:
        return settings.wecom_robot_webhook_url
    if settings.wecom_robot_webhook_key:
        return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={settings.wecom_robot_webhook_key}"
    return ""


def send_robot_message(content: str, msgtype: str = "text", mentioned_list: list[str] | None = None) -> dict[str, Any]:
    url = robot_webhook_url()
    if not url:
        return {"skipped": True, "reason": "WECOM_ROBOT_WEBHOOK_URL or WECOM_ROBOT_WEBHOOK_KEY is not configured"}
    if msgtype == "markdown":
        payload: dict[str, Any] = {"msgtype": "markdown", "markdown": {"content": content}}
    else:
        payload = {"msgtype": "text", "text": {"content": content}}
        if mentioned_list:
            payload["text"]["mentioned_list"] = mentioned_list
    with httpx.Client(timeout=settings.ai_request_timeout_seconds) as client:
        resp = client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()
