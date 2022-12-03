class Predicate:
    """A closure of a name and arity"""

    def __init__(self, name, arity):
        # values must not be mutated after initial assignment, 
        #  otherwise hashing locations change
        self.name = name
        self.arity = arity

    def __eq__(self, other):
        return self.name == other.name and self.arity == other.arity

    def __hash__(self):
        return hash((self.name, self.arity))

    def __str__(self):
        return "%s/%d" % (self.name, self.arity)


def predicate_dependency(predicate_dependency_map, predicate1, predicate2):
    """
        Given two predicates and a map of each predicate to a list of
            predicates it depends on (hence a directed graph of dependencies)
        Returns True if predicate1 is dependent (directly or indirectly)
            on predicate2
    """

    visited = set()
    stack = [predicate1]
    while stack:
        current_predicate = stack.pop()

        if current_predicate == predicate2:
            return True

        if current_predicate not in visited:
            if current_predicate in predicate_dependency_map.keys():
                stack.extend(predicate_dependency_map[current_predicate].difference(visited))  # dfs

    return False
