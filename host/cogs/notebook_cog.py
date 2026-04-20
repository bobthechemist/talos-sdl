# host/cogs/notebook_cog.py
from host.cogs.base_cog import BaseCog
from host.gui.console import C

class NotebookCog(BaseCog):
    """Handles notebook administration and manual data entry."""

    def get_commands(self):
        return {
            "/note": self.handle_note
        }

    def handle_note(self, *args):
        """Adds a manual note to the DLN science log. Usage: /note <your note>"""
        content = " ".join(args)
        if not content:
            print(f"{C.ERR}Usage: /note <your note content>{C.END}")
            return
        
        # Log the note directly into the science log
        log_id = self.dln.log_science(
            entry_type="note", 
            data={"message": content}
        )
        
        print(f"{C.OK}Note recorded (ID: {log_id}).{C.END}")