## Command line interface

You can use the command line interface (CLI) to run `datafusion`

To import data into your database, run the following commands in the specified order:

Load data from the Topographic Objects Database ([source](https://www.geoportal.gov.pl/pl/dane/baza-danych-obiektow-topograficznech-bdot10k/)):
```bash
bdot -c config.yml
```

Load data from the Administrative Boundaries - part of the State Register of Boundaries ([source](https://www.geoportal.gov.pl/pl/dane/panstwowy-rejestr-granic-prg/))
```bash
borders -c config.yml
```

Load data from the Terrain Utilities Network ([source](https://www.geoportal.gov.pl/pl/dane/uzbrojenie-terenu-gesut/))
```bash
kiut -c config.yml
```

Load data from a xlsx file prepared by the user, which contains heating data ([source](https://www.gunb.gov.pl/podmenu/1713))
```bash
ceeb -c config.yml

```

Load data from the National Register of Borders ([source](https://www.geoportal.gov.pl/pl/dane/panstwowy-rejestr-granic-prg/))
```bash
prg -c config.yml
```

> **_WARNING:_** Running commands in a different order may cause errors. Each script may depend on the previous one.