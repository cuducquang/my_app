def register_tools(registry):
    def family_budget_buffer(people: int = 4, buffer_percent: int = 10):
        return {
            "people": people,
            "buffer_percent": buffer_percent,
            "message": "Recommended extra buffer for family trips.",
        }

    registry.register_simple(
        name="family_budget_buffer",
        description="Suggest a buffer percent for family trips",
        schema={"people": "int", "buffer_percent": "int"},
        handler=family_budget_buffer,
    )

