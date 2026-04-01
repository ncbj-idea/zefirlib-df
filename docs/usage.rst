How to use?
======================

You can use the command line interface (CLI) to run `datafusion`.

To import data into your database, run the following commands in the specified order:

Load data from the Topographic Objects Database
(`source <https://www.geoportal.gov.pl/pl/dane/baza-danych-obiektow-topograficznech-bdot10k/>`_):

.. code-block:: bash

   bdot -c config.yml

Load data from the Administrative Boundaries - part of the State Register of Boundaries
(`source <https://www.geoportal.gov.pl/pl/dane/panstwowy-rejestr-granic-prg/>`_):

.. code-block:: bash

   borders -c config.yml

Load data from the Terrain Utilities Network
(`source <https://www.geoportal.gov.pl/pl/dane/uzbrojenie-terenu-gesut/>`_):

.. code-block:: bash

   kiut -c config.yml

Load data from a xlsx file prepared by the user, which contains heating data
(`source <https://www.gunb.gov.pl/podmenu/1713>`_):

.. code-block:: bash

   ceeb -c config.yml

Load data from the National Register of Borders
(`source <https://www.geoportal.gov.pl/pl/dane/panstwowy-rejestr-granic-prg/>`_):

.. code-block:: bash

   prg -c config.yml

.. warning::

Running commands in a different order may cause errors. Each script may depend on the previous one.
Load data from PVGIS database
.. code-block:: bash

   pvgis -c config.yml
Merge procedure from PVGIS database and Address database
.. code-block:: bash

   pvgis_merger -c config.yml