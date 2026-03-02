from gi.repository import Gtk

class CustomWidget(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.label = Gtk.Label(label="This is a custom widget")
        self.button = Gtk.Button(label="Click Me")
        self.button.connect("clicked", self.on_button_clicked)

        self.pack_start(self.label, True, True, 0)
        self.pack_start(self.button, True, True, 0)

    def on_button_clicked(self, widget):
        self.label.set_text("Button Clicked!")