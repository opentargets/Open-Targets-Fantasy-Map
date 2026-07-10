import unittest

from ot_fmg.ontology import OntologyResolver


class OntologyResolverTests(unittest.TestCase):
    def test_primary_path_prefers_larger_parent_branch_then_shorter_then_lexical(self):
        edges = [
            {"child": "A", "parent": "ROOT"},
            {"child": "B", "parent": "ROOT"},
            {"child": "A1", "parent": "A"},
            {"child": "A2", "parent": "A"},
            {"child": "B1", "parent": "B"},
            {"child": "D1", "parent": "A1"},
            {"child": "D2", "parent": "A2"},
            {"child": "D3", "parent": "B1"},
            {"child": "D4", "parent": "A1"},
            {"child": "D4", "parent": "B1"},
        ]
        resolver = OntologyResolver(["D1", "D2", "D3", "D4"], edges, "child", "parent", root_ids=["ROOT"])
        assignment = resolver.assign("D4")
        self.assertEqual(assignment.path, ("ROOT", "A", "A1", "D4"))
        self.assertEqual(assignment.state_id, "A")
        self.assertEqual(assignment.province_id, "A1")
        self.assertEqual(assignment.extra_parents, ("B1",))

    def test_disease_without_second_level_becomes_its_own_province(self):
        edges = [{"child": "D1", "parent": "ROOT"}]
        resolver = OntologyResolver(["D1"], edges, "child", "parent", root_ids=["ROOT"])
        assignment = resolver.assign("D1")
        self.assertEqual(assignment.state_id, "D1")
        self.assertEqual(assignment.province_id, "D1")


if __name__ == "__main__":
    unittest.main()
