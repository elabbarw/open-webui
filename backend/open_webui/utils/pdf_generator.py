from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, List
from html import escape

from markdown import markdown

import site

import re
import arabic_reshaper
from bidi.algorithm import get_display
import textwrap

from fpdf import FPDF

from open_webui.env import STATIC_DIR, FONTS_DIR
from open_webui.models.chats import ChatTitleMessagesForm

# Regular expression to capture various RTL scripts including Arabic, Hebrew, Syriac, Thaana, and Samaritan.
rtl_re = re.compile(
    r'[\u0600-\u06FF\u0590-\u05FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u0700-\u074F\u0780-\u07BF]'
)

def contains_rtl(text: str) -> bool:
    """Return True if the text contains RTL characters from supported languages."""
    return bool(rtl_re.search(text))

def fix_rtl(text: str, width: int = 75) -> str:
    """
    Adjust the display of right-to-left text line by line.
    For Arabic, each line is reshaped individually before applying the bidi algorithm.
    """
    wrapped_lines = textwrap.wrap(text, width=width) # Wrap the text so we avoid it rendering in reverse
    processed_lines = []
    for line in wrapped_lines:
        if re.search(r'[\u0600-\u06FF]', line):  # Only Arabic-like text requires reshaping.
            line = arabic_reshaper.reshape(line)
        processed_lines.append(get_display(line))
    return "\n".join(processed_lines)

class PDFGenerator:
    """
    Description:
    The `PDFGenerator` class is designed to create PDF documents from chat messages.
    The process involves transforming markdown content into HTML and then into a PDF format

    Attributes:
    - `form_data`: An instance of `ChatTitleMessagesForm` containing title and messages.

    """

    def __init__(self, form_data: ChatTitleMessagesForm):
        self.html_body = None
        self.messages_html = None
        self.form_data = form_data

        self.css = Path(STATIC_DIR / "assets" / "pdf-style.css").read_text()

    def format_timestamp(self, timestamp: float) -> str:
        """Convert a UNIX timestamp to a formatted date string."""
        try:
            date_time = datetime.fromtimestamp(timestamp)
            return date_time.strftime("%Y-%m-%d, %H:%M:%S")
        except (ValueError, TypeError) as e:
            # Log the error if necessary
            return ""

    def _build_html_message(self, message: Dict[str, Any]) -> str:
        """Build HTML for a single message."""
        role = escape(message.get("role", "user"))
        content = escape(message.get("content", ""))
        if contains_rtl(content):
            content = fix_rtl(content)
        timestamp = message.get("timestamp")

        model = escape(message.get("model") if role == "assistant" else "")

        date_str = escape(self.format_timestamp(timestamp) if timestamp else "")

        # extends pymdownx extension to convert markdown to html.
        # - https://facelessuser.github.io/pymdown-extensions/usage_notes/
        # html_content = markdown(content, extensions=["pymdownx.extra"])

        content = content.replace("\n", "<br/>")
        html_message = f"""
            <div>
                <div>
                    <h4>
                        <strong>{role.title()}</strong>
                        <span style="font-size: 12px;">{model}</span>
                    </h4>
                    <div> {date_str} </div>
                </div>
                <br/>
                <br/>

                <div>
                    {content}
                </div>
            </div>
            <br/>
          """
        return html_message

    def _generate_html_body(self) -> str:
        """Generate the full HTML body for the PDF."""
        title = self.form_data.title
        if contains_rtl(title):
            title = fix_rtl(title)
        escaped_title = escape(title)
        return f"""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            </head>
            <body>
            <div>
                <div>
                    <h2>{escaped_title}</h2>
                    {self.messages_html}
                </div>
            </div>
            </body>
        </html>
        """

    def generate_chat_pdf(self) -> bytes:
        """
        Generate a PDF from chat messages.
        """
        try:
            global FONTS_DIR

            pdf = FPDF()
            pdf.add_page()

            # When running using `pip install` the static directory is in the site packages.
            if not FONTS_DIR.exists():
                FONTS_DIR = Path(site.getsitepackages()[0]) / "static/fonts"
            # When running using `pip install -e .` the static directory is in the site packages.
            # This path only works if `open-webui serve` is run from the root of this project.
            if not FONTS_DIR.exists():
                FONTS_DIR = Path("./backend/static/fonts")

            pdf.add_font("NotoSans", "", f"{FONTS_DIR}/NotoSans-Regular.ttf")
            pdf.add_font("NotoSans", "b", f"{FONTS_DIR}/NotoSans-Bold.ttf")
            pdf.add_font("NotoSans", "i", f"{FONTS_DIR}/NotoSans-Italic.ttf")
            pdf.add_font("NotoSansKR", "", f"{FONTS_DIR}/NotoSansKR-Regular.ttf")
            pdf.add_font("NotoSansJP", "", f"{FONTS_DIR}/NotoSansJP-Regular.ttf")
            pdf.add_font("NotoSansSC", "", f"{FONTS_DIR}/NotoSansSC-Regular.ttf")
            pdf.add_font("NotoSansArabic", "", f"{FONTS_DIR}/NotoSansArabic-Regular.ttf")
            pdf.add_font("NotoSansHebrew", "", f"{FONTS_DIR}/NotoSansHebrew-Regular.ttf")
            pdf.add_font("NotoSansSyriac", "", f"{FONTS_DIR}/NotoSansSyriac-Regular.ttf")
            pdf.add_font("NotoSansThaana", "", f"{FONTS_DIR}/NotoSansThaana-Regular.ttf")
            pdf.add_font("NotoSansSamaritan", "", f"{FONTS_DIR}/NotoSansSamaritan-Regular.ttf")
            pdf.add_font("Twemoji", "", f"{FONTS_DIR}/Twemoji.ttf")

            pdf.set_font("NotoSans", size=12)
            pdf.set_fallback_fonts(
                [
                    "NotoSansKR", 
                    "NotoSansJP", 
                    "NotoSansSC", 
                    "NotoSansArabic", 
                    "NotoSansHebrew", 
                    "NotoSansSyriac",
                    "NotoSansThaana",
                    "NotoSansSamaritan",
                    "Twemoji"
                ]
            )

            pdf.set_auto_page_break(auto=True, margin=15)

            # Build HTML messages
            messages_html_list: List[str] = [
                self._build_html_message(msg) for msg in self.form_data.messages
            ]
            self.messages_html = "<div>" + "".join(messages_html_list) + "</div>"

            # Generate full HTML body
            self.html_body = self._generate_html_body()

            pdf.write_html(self.html_body)

            # Save the pdf with name .pdf
            pdf_bytes = pdf.output()

            return bytes(pdf_bytes)
        except Exception as e:
            raise e
