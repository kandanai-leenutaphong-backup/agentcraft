import unittest

from pipeline import Pipeline


class PipelineTests(unittest.TestCase):
    def test_composes_in_list_order(self):
        pipeline = Pipeline([
            lambda data: data["values"],
            sum,
            lambda total: {"doubled": total * 2},
        ])
        self.assertEqual(pipeline({"values": [1, 2, 3]}), {"doubled": 12})
        self.assertEqual(pipeline({"values": [4]}), {"doubled": 8})

    def test_empty_pipeline_returns_input(self):
        data = {"values": [1, 2, 3]}
        self.assertIs(Pipeline([])(data), data)

    def test_pipeline_is_a_function_in_another_pipeline(self):
        double = Pipeline([lambda value: value * 2])
        pipeline = Pipeline([double, lambda value: value + 1])
        self.assertEqual(pipeline(3), 7)

    def test_error_propagates_without_running_later_functions(self):
        visited = []
        failure = ValueError("invalid input")

        def fail(data):
            raise failure

        pipeline = Pipeline([fail, visited.append])
        with self.assertRaises(ValueError) as raised:
            pipeline(3)
        self.assertIs(raised.exception, failure)
        self.assertEqual(visited, [])


if __name__ == "__main__":
    unittest.main()