R scripts description
=================

Value of parameters can be represented in three forms:

-  single numerical or integer value.
-  single string value - one or more quoted words.
-  expression - phrase which is preceded by !expr. It tells function
   that expression should be evaluated as R expression (code chunk),
   instead simple loading variable. It allows use vectors, list (overall
   more complex objects) in config file.

Symbol “>” afted !expr comes from yml syntax and allows for line
breaking for better readability.

In config file all space in data column name need be replaced by “_“.
There are declared in the config file due to the possibility of changing
them (external data source). The same reason is for feature values.

Parameters
==========

Parameters are divided in 5 categories:

-  params - basic modification how some operation are evaluated,
-  ceeb_params - parameteres related to CEEB data,
-  bdot_params - parameters related to building data,
-  joining_params - parameters responsible for how correction in merging
   CEEB and building data are made,
-  default - don’t change, technical requirement of config library.

.. raw:: latex

   \begin{center}
   \LARGE params
   \end{center}

| **h3_resolution** - integer parameter related to resolution of
  hexagons (h3 method) and it is used in multi-criteria decision. It
  needs to be a number between 5 and 10, where 10 should be used in
  small JST and 5 in big cities or similar area. Other values will cause
  error.
| **gini_in_topsis** - logical parameter responsible for using gini in
  multi-criteria-decision. It should be FALSE now, because gini
  incorporation require automated evaluation in non-continuous results.
| **gini_lorenz** - logical parameter. Should lorenze curve used in
  calculation of gini index.
| **gini_method** - string parameter. Method of gini calculation,
  allowed values: trapz or aprox.
| **classification_method** - string parameter. Which method should be
  used in multi-criteria decision. Allowed values: average, volatility,
  distance and topsis. Default is topsis, it usually has the best
  results.
| **coord_system** - string parameter, default EPSG:2180. Coordinated
  system is used in config file for elasticity reason, if some building
  data come from different system.
| **complex_distance** - numerical parameter. Responsible for maximum
  distance in non living building shapes merging.
| **string_max_distance** - numerical parameter between 0 and 1.
  Threshold in string dissimilarity, lower value cause more strict
  joining, greater more loose. In method cosine with parameter value 1,
  the best results so far is with string_max_distance equal 0.1.
| **string_param** - numerical parameter. Parameters used string
  dissimilarity methods. If string_method is ‘jw’ than allowed values
  are 0-0.25 otherwise integer between 1-5.
| **string_method** - string parameter. Which method should be used in
  string dissimilarity methods. Allowed values: “osa”, “lv”, “dl”,
  “hamming”, “lcs”, “qgram”, “cosine”, “jaccard”, “jw”,“soundex”.
  Default cosine (best results).
| **heat_threshold** - numerical parameter in multi-criteria-decision.
  Describe which hexagon should treated as connected to heat. Allowed
  values are 0.25-0.75. Lower value less strict requirement for positive
  heat connectivity. Default is 0.5.
| **heat_development** - string parameter. Which method should be used
  in future of heat development. Allowed values are: “h3”,
  “none”,“distance”.
| **expanded_logs** - logical values Should be printed more logs.
  Default is true.

.. raw:: latex

   \begin{center}
   \LARGE ceeb\_params
   \end{center}

| **ceeb_merger** - expression, which columns should be used in merging
  ceeb reports.
| **ceeb_boiler** - expression, which feature values should be present
  in *ceeb_device_col* to merge CEEB reports.
| **ceeb_summary** - expression, which columns are not allowed to have
  missing value (discard records with missing value).
| **ceeb_living** - expression, feature values in *ceeb_declare_col*
  which points to the declaration regarding residential buildings.
| **ceeb_non_living** - as above, but non residential buildings.
| **ceeb_diverge** - string, column name, technical correction in naming
  between ceeb reports.
| **ceeb_device_col** - string, column name, refers to declared device.
| **ceeb_street_col** - string, column name, refers to street name’s.
| **ceeb_number_col** - string, column name, refers to address number’s.
| **ceeb_class_col** - string, column name, refers to class of device.
| **ceeb_declare_col** - string, column name, refers to declaration type
  (living/nonliving).
| **ceeb_eksp_col** - string, column name, refers to number of used
  devices.
| **ceeb_nmb_col** - string, column name, refers to number of installed
  devices.
| **ceeb_lokal_col** - string, column name, refers to apartment number.

.. raw:: latex

   \begin{center}
   \LARGE bdot\_params
   \end{center}

| **bdot_street_col** - string, column name, refers to street name’s.
| **bdot_number_col** - string, column name, refers to address number’s.
| **bdot_geom_var** - string, column name, refers to geometry.
| **bdot_binary_var** - expresion, column names, in merging shapes, on
  which columns should be used logical function *any*./ **bdot_sum_var**
  - expresion, column names, in merging shapes, on which columns should
  be used summarise function *sum*./ **bdot_addr_var** - expresion,
  column names, in merging shapes, on which columns should be take
  values form address building.
| **bdot_addr_distance** - string, column name, refers to distance to
  address point.
| **bdot_id** - string, column name, refers to id.
| **bdot_merge_var** - string, column name, refers to building type
  (that with lower number of category). It is used in merging shapes
  procedure and merge correction.
| **bdot_col_output** - expresion, column names, tells which columns
  should be keep after some operations.
| **h3_excluded_type** - expresion, feature values, which building type
  in *bdot_detail* should be excluded from multi-criteria-decion.
| **bdot_floors** - string, column name, refers to number of floors.
| **bdot_pow_uzytkow** - string, column name, refers to area of
  building.
| **bdot_obrys** - string, column name, refers to area of shape.
| **bdot_detail** - string, column name, refers to building type (that
  with greater number of category). It is used in
  multi-criteria-decision and exluding unheated buildings.
| **bdot_heat** - string, column name, refers to heat connectivity based
  on distance.
| **heat_distance** - string, column name, refers to hdistance from heat
  network.
| **non_inventory_build** - expresion, feature values, which building
  type in *bdot_detail* should be treated as unheated.
| **living_bdot** - expresion, column names, which records should be
  treated as residential building, based on value in *bdot_merge_var*.

.. raw:: latex

   \begin{center}
   \LARGE joining\_params
   \end{center}

| **var_ceeb** - string, column name, refer to type of residential
  building.
| **ceeb_single** - string, feature value, refer to single family house.
| **ceeb_multi** - string, feature value, refer to multi family house.
| **ceeb_other** - string, feature value, refer to collective housing
  buildings.
| **single_order** - expression, order of single family correction in
  merging ceeb and building data. Those values are from building data
  (*bdot_merge_var*).
| **multi_order** - as above, but for multi family residential.
| **other_order** - as above, but for collective housing buildings.
| **nonliving_order** - as above, but for non residential building.
  Important: reverse order. It is used in separate function, iteratively
  not merge with contained building types. In each iteration is removed
  first position of vector.
