from .base import RawDocument


class TxtLoader:
    async def load(self, file_path: str):
        with open(file_path, encoding="utf-8") as f:
            text = f.read()

        return RawDocument(text=text, title=file_path.split("/")[-1], source=file_path, metadata={})
