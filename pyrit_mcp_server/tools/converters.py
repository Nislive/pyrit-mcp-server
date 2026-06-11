"""MCP tools for PyRIT prompt converters."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from pyrit_mcp_server.core import ensure_memory

# Converters that work without an LLM target (text → text, no external deps).
_SIMPLE_CONVERTERS: dict[str, str] = {
    "base64": "Base64Converter",
    "rot13": "ROT13Converter",
    "caesar": "CaesarConverter",
    "binary": "BinaryConverter",
    "morse": "MorseConverter",
    "leetspeak": "LeetspeakConverter",
    "atbash": "AtbashConverter",
    "braille": "BrailleConverter",
    "ascii_art": "AsciiArtConverter",
    "unicode_confusable": "UnicodeConfusableConverter",
    "zero_width": "ZeroWidthConverter",
    "zalgo": "ZalgoConverter",
    "string_join": "StringJoinConverter",
    "flip": "FlipConverter",
    "superscript": "SuperscriptConverter",
    "character_space": "CharacterSpaceConverter",
    "diacritic": "DiacriticConverter",
    "random_capital": "RandomCapitalLettersConverter",
    "suffix_append": "SuffixAppendConverter",
    "repeat_token": "RepeatTokenConverter",
    "insert_punctuation": "InsertPunctuationConverter",
    "nato": "NatoConverter",
    "charswap": "CharSwapConverter",
    "bidi": "BidiConverter",
    "noise": "NoiseConverter",
    "base2048": "Base2048Converter",
    "ecoji": "EcojiConverter",
    "bin_ascii": "BinAsciiConverter",
    "json_string": "JsonStringConverter",
    "first_letter": "FirstLetterConverter",
    "tatweel": "TatweelConverter",
    "arabic_presentation_form": "ArabicPresentationFormConverter",
}


def _get_converter(name: str):  # noqa: ANN202
    """Resolve a converter name to an instance."""
    import pyrit.prompt_converter as pc

    cls_name = _SIMPLE_CONVERTERS.get(name)
    if not cls_name:
        raise ValueError(
            f"Unknown converter '{name}'. Available: {list(_SIMPLE_CONVERTERS.keys())}"
        )
    cls = getattr(pc, cls_name)
    return cls()


def register(mcp: FastMCP) -> None:
    """Register converter tools on the MCP server."""

    @mcp.tool()
    async def convert_prompt(
        text: str,
        converter_name: str,
    ) -> dict[str, Any]:
        """Convert a prompt using a single converter.

        Args:
            text: The prompt text to convert.
            converter_name: Name of the converter (e.g. base64, rot13, leetspeak).
                Use list_converters to see all available names.

        Returns:
            Dict with converted text and output type.
        """
        try:
            ensure_memory()
            converter = _get_converter(converter_name)
            result = await converter.convert_async(prompt=text)
            return {
                "status": "success",
                "converter": converter_name,
                "output_text": result.output_text,
                "output_type": result.output_type,
            }
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def chain_convert(
        text: str,
        converter_names: list[str],
    ) -> dict[str, Any]:
        """Apply multiple converters in sequence.

        Args:
            text: The prompt text to convert.
            converter_names: List of converter names to apply in order.

        Returns:
            Dict with final converted text and each step's output.
        """
        try:
            ensure_memory()
            steps = []
            current = text
            for name in converter_names:
                converter = _get_converter(name)
                result = await converter.convert_async(prompt=current)
                steps.append({
                    "converter": name,
                    "output_text": result.output_text,
                    "output_type": result.output_type,
                })
                current = result.output_text

            return {
                "status": "success",
                "final_text": current,
                "steps": steps,
            }
        except Exception as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    @mcp.tool()
    async def list_converters() -> dict[str, Any]:
        """List all available prompt converters.

        Returns:
            Dict with converter names and their PyRIT class names.
        """
        return {"status": "success", "converters": _SIMPLE_CONVERTERS}
