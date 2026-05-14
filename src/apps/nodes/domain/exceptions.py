class NodeNotFound(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Node not found: {name}")
        self.name = name
