{% docs semantic_layer %}

The semantic layer is a deliberately thin BI-facing naming and documentation
layer over the authoritative Iceberg Silver and Gold tables.

It does not resolve `business_version`, perform targeted overwrites, or rebuild
the D-4 Gold aggregate. Those responsibilities remain with the PyIceberg
medallion and its existing Gold ownership contract.

{% enddocs %}
