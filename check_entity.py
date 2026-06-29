import sys
sys.path.insert(0, 'services')
from knowledge_graph.graph_store import get_driver

d = get_driver()
result = d.session().run("MATCH (e:Entity) WHERE toLower(e.name) CONTAINS 'nodenotready' RETURN e.name, e.type, e.description")
records = list(result)
print('Matches:', len(records))
for r in records:
    print(r)
d.close()