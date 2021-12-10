# Openquake resources

 - https://www.globalquakemodel.org/openquake

## User guidance

 - https://docs.openquake.org/oq-engine/advanced/introduction.html
 - https://docs.openquake.org/oq-engine/advanced/common-mistakes.html
 - [The Manual](https://docs.openquake.org/manuals/OpenQuake%20Manual%20%28latest%29.pdf)

## Developer/Testing

 - https://github.com/gem/oq-engine/blob/master/doc/installing/development.md
 - https://github.com/gem/oq-engine/blob/master/doc/testing.md
 - https://github.com/gem/oq-engine/blob/engine-3.12/doc/running/unix.md


## The opensha (ucerf) converter

 - https://gitlab.openquake.org/hazard/converters/ucerf/-/tree/feature/add_nz_crustal_modular_support


## Running our DOcker image

```
 docker run  -it --rm \
 -v $(pwd)/examples:/WORKING/examples \
 -v $(pwd)/../../../ucerf:/app/ucerf \
 b37fc487d49c  -s bash
 ```