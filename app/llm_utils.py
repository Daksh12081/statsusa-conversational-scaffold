def response_text(response) -> str:
    content = response.content

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(text)
            elif hasattr(item, "text"):
                text = getattr(item, "text", None)
                if text:
                    parts.append(text)

        return "\n".join(parts).strip()

    return str(content).strip()
