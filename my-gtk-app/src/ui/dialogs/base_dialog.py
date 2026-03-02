from gi.repository import Gtk

class BaseDialog(Gtk.Dialog):
    def __init__(self, title, parent=None, modal=True):
        super().__init__(title=title, parent=parent, modal=modal)
        self.set_default_size(400, 300)
        self.set_resizable(False)

        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        self.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)

    def run_dialog(self):
        response = self.run()
        self.hide()
        return response

    def close_dialog(self):
        self.hide()