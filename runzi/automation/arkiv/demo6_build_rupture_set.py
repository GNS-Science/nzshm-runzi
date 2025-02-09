from py4j.java_gateway import JavaGateway

gateway = JavaGateway()
app = gateway.entry_point

builder = app.getBuilder()
result = (
    builder.setMaxFaultSections(100)
    .setMaxJumpDistance(2.33)
    .buildRuptureSet("./data/FaultModels/DEMO2_DIPFIX_crustal_opensha.xml")
)

builder.writeRuptureSet('/tmp/XXX.zip')
