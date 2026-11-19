# iPhone-import

Anslut en upplåst iPhone med en USB-datakabel. Tryck på **Lita på** om telefonen frågar. Öppna GNOME Filer och välj telefonen bland enheterna i sidofältet för att bläddra bland de filer som telefonen delar via USB. Du kan också öppna **iPhone-import**, välja telefonen och klicka på **Visa iPhone i Filer**. Appen monterar telefonens medievolym automatiskt så att DCIM blir åtkomlig, även om GNOME från början bara visar dokumentvolymen.

För att kopiera bilder och videor från telefonens DCIM-mapp, välj en lokal målmapp i **iPhone-import** och klicka på **Importera bilder och videor**. Identiska filer hoppas över. Filer med samma namn och olika innehåll sparas båda. Importen lämnar originalen kvar på telefonen. Målfilsystemet behöver stöd för hårda länkar, som ext4.

## Bygg och installera

Med `gettext` och `dpkg-deb` tillgängliga, kör `./build-package.sh .` och sedan `sudo apt install ./iphone-import_0.1.1_all.deb`.
