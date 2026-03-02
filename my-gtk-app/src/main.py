import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import os

class MyApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.example.mygtkapp')
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = self.create_main_window()
        self.window.show_all()

    def create_main_window(self):
        builder = Gtk.Builder()
        ui_file_path = os.path.join(os.path.dirname(__file__), 'ui', 'glade', 'main_window.ui')
        builder.add_from_file(ui_file_path)
        window = builder.get_object('main_window')
        window.connect('destroy', self.on_window_destroy)
        return window

    def on_window_destroy(self, widget):
        self.quit()

if __name__ == '__main__':
    app = MyApp()
    app.run()