# TODO

### Site lists

   Can you pls supply a table for each of your location lists that includes a site code from  https://service.unece.org/trade/locode/nz.htm. A simple google spreadsheet would be perfect.
   - NB unfortunately the OQ sites_csv doesn't support extra fields, so we'll need to build the csvs from the tables. I can easily automate this.
   - NB We're using the  LOCODE column but ignoring the COUNTRY section (since everything is NZ) to identity locations across the NZSHM services, so it'd be very helpful to make sure our hazard sites are also 'known' locations.


## ID in source -ruptures.xml

Toshi ID may contain `=` e.g. `SW52ZXJzaW9uU29sdXRpb246NTYyNC4wUnZKeFg=`

This cannot be used to identify source models . Manual testing replaced `=` with `_`

## ini fixes


### sites
 ```
[geometry]

#site_model_file = nz_towns_4.csv
sites_csv = nz_towns_4.csv
```

### distances

`maximum_distance = {'Active Shallow Crust': 300.0, 'Volcanic': 300, 'Subduction Interface': 400, 'default': 400}`
