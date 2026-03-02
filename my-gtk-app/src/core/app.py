from gi.repository import Gtk

class MyApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.example.mygtkapp")
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = Gtk.Builder()
            self.window.add_from_file("src/ui/glade/main_window.ui")
            self.window.connect_signals(self)
            self.window.show_all()

    def on_window_destroy(self, widget):
        self.quit()

if __name__ == "__main__":
    app = MyApp()
    app.run()