"""Channel adapters — let one conversation engine serve multiple platforms.

Each channel exposes the same three methods the engine calls:
    send_text(to, body)
    send_buttons(to, body, buttons, header=None)         buttons: [(id, title)]
    send_list(to, body, button_text, rows, header=None, footer=None)
                                                         rows: [(id, title, desc)]

WhatsApp renders native buttons/lists. Messenger & Instagram render the same
choices as tappable "quick replies".
"""
import whatsapp_api as wa
import messenger_api as mg


class WhatsAppChannel:
    name = "whatsapp"

    def send_text(self, to, body):
        return wa.send_text(to, body)

    def send_buttons(self, to, body, buttons, header=None):
        return wa.send_buttons(to, body, buttons, header)

    def send_list(self, to, body, button_text, rows, header=None, footer=None):
        return wa.send_list(to, body, button_text, rows, header, footer)


class MessengerChannel:
    """Works for both Facebook Messenger and Instagram (same Send API shape)."""

    def __init__(self, platform="messenger"):
        self.name = platform  # "messenger" or "instagram"

    def send_text(self, to, body):
        return mg.send_text(to, body, platform=self.name)

    def send_buttons(self, to, body, buttons, header=None):
        text = (header + "\n\n" + body) if header else body
        return mg.send_quick_replies(to, text, [(bid, title) for bid, title in buttons], platform=self.name)

    def send_list(self, to, body, button_text, rows, header=None, footer=None):
        text = (header + "\n\n" + body) if header else body
        if footer:
            text += "\n\n" + footer
        return mg.send_quick_replies(to, text, [(rid, title) for rid, title, desc in rows], platform=self.name)
