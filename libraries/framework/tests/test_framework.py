import unittest

from agentcraft import Binding, Framework, FrameworkError


class Resource:
    def __init__(self, name, events):
        self.name, self.events = name, events

    async def read(self):
        return {"value": 7}

    async def aclose(self):
        self.events.append(self.name)


class FrameworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_bindings_offline_description_and_reverse_owned_close(self):
        events = []
        data, model, borrowed = (Resource(name, events) for name in ("data", "model", "borrowed"))
        app = Framework({"data": Binding("data.query", data, owned=True),
                         "model": Binding("model.chat", model, owned=True, requires=("data",)),
                         "view": Binding("view.text", borrowed),
                         "alias": Binding("data.query", data, owned=True)})
        self.assertEqual(events, [])
        self.assertEqual(app.describe()["readiness"], "unverified")
        async with app:
            self.assertEqual(await app.get("data", Resource).read(), {"value": 7})
            with self.assertRaises(FrameworkError):
                app.get("missing", Resource)
            with self.assertRaises(FrameworkError):
                app.get("data", str)
        await app.aclose()
        self.assertEqual(events, ["model", "data"])
        with self.assertRaises(FrameworkError):
            app.get("data", Resource)

    async def test_unknown_dependency_and_cycles_refuse_before_lifecycle(self):
        events = []
        value = Resource("one", events)
        for bindings in ({"one": Binding("fixture.read", value, requires=("missing",))},
                         {"one": Binding("fixture.read", value, requires=("two",)),
                          "two": Binding("fixture.read", value, requires=("one",))}):
            with self.assertRaises(ValueError):
                Framework(bindings)
        self.assertEqual(events, [])