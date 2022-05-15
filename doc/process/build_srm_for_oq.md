# Build SRM

## Outline
1. Crustal Inversion Sources
2. Subduction Inversion Sources
3. Distributed Seismicity Model


### Crustal Inversion Source
1. Use same distributed seismicity model that will be used in hazard calculation
2. Run inversion on (N,b) combination
3. Scale rates to account for polygon function (typically 80%)
    - this is only to be applied up to M8
4. Scale rates for scaling of N (on top of step 3)
5. convert to NRML

### Subduction Inversion Source
1. Run inversion
2. Scale rates for scaling of N (on top of step 3)
3. convert to NRML

### Distributed Seismicity
1. Create rates for (N,b) combination
2. Reduce rates in polygons using output from Crustal step 2
3. Scale N same amount as in Crustal step 4

### Combining Sources into a Single Logic Tree Branch
- Crustal Inverion (N,b) paired with distributed N,b
- Crustal scaled N paired with distributed scaled N
- All combinations of subduction [(N,b) and scaling] with Crustal [(N,b) and scaling]
- Combine distributed seismicity [(N,b) and scaling] with matching Crustal [(N,b) and scaling]