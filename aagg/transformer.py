import clingo
from equivalence_transformer import EquivalenceTransformer
from ast_visitor import ASTReplacer, ASTPoolInstantiator, ASTPredicateMapper


class Transformer:
    """
        This class is the basis of rewrites on the logic program.
        Stores a reference of every rule in the program (for debugging purposes)
        Invokes EquivalenceTransformer per rule for rewriting.
    """

    def __init__(self, builder, setting, output_file_descriptor):
        self.builder = builder
        self.Setting = setting
        self.out_fd = output_file_descriptor

        self.astReplacer = ASTReplacer()
        self.astPoolInstantiator = ASTPoolInstantiator()
        self.predicate_mapper = ASTPredicateMapper()
        self.input_statements = []
        self.output_statements = []
        self.predicate_adjacency_list = {}
        self.in_predicates = set()
        self.new_predicates = set()

    def add_statement(self, stm):
        self.input_statements.extend(self.preprocess_statement(stm))

    def preprocess_statement(self, stm):
        """
            Given a statement.
            Replaces AST objects in the rule, those which have non-Gringo syntax
                string representations, with custom-defined AST objects for
                which the __str__ method is overridden
            Then, if a (or multiple) pools exist within the statement,
                instantiate the statement into a set of multiple equivalent
                statements, where each contains no pools
            Returns the preprocessed statement(s)
        """
        stm = self.astReplacer.replace(stm)

        pool_instantiated_rules = []
        for instantiation in self.astPoolInstantiator.instantiate_pools(stm):
            pool_instantiated_rules.append(instantiation)

        return pool_instantiated_rules

    def explore_statements(self):
        """
            Explores the input statements. Traverses each rule to:
            1) Create an adjacency list of predicate dependencies which
                is later used to determine 'safety' or rewriting to 
                output forms (2) and (3).
            2) Develop a set of all predicates in the input program 
                which is later used to avoid naming collisions that may
                occur when introducing new function names during rule
                rewriting (for if projection must be used)
        """
        for stm in self.input_statements:
            self.predicate_mapper.map_rule_predicates(stm)
        self.predicate_adjacency_list = self.predicate_mapper.predicate_map

        if self.Setting.DEBUG:
            self.print_predicate_graph()

        self.in_predicates.update(set(self.predicate_adjacency_list.keys()))
        for predicate_set in self.predicate_adjacency_list.values():
            self.in_predicates.update(predicate_set)

    def transform_statements(self):
        """
            Transforms each statement via equivalence rewriting.
            The transform_rule function returns a list, for the case 
                when a projection rule is created
        """
        if self.Setting.NO_REWRITE:
            self.output_statements = self.input_statements

        else:
            for statement in self.input_statements:
                parsed_statements = self.transform_rule(statement)
                for parsed_statement in parsed_statements:
                    self.output_statements.append(parsed_statement)

    def write_statements(self):
        """
            Writes output statements to the given file descriptor, 
                correcting any potential output errors
        """
        for statement in self.output_statements:
            statement_str = "%s" % statement
            self.out_fd.write(statement_str + "\n")

    def build_statements(self):
        """
            Using the builder, adds each statement to the clingo program
                for potential grounding and solving later. 
            This is also useful for checking potential errors in 
                rewritten statements.
        """
        for statement in self.output_statements:
            self.builder.add(statement)

    def transform_rule(self, statement):
        """
            Transforms rule using EquivalenceTransformer class
            Returns outputted rule, whether transformed or not.
                If an auxiliary rule was created, returns that too.
        """
        if not isinstance(statement, clingo.ast.AST) or \
                statement.type != clingo.ast.ASTType.Rule:
            return [statement]

        else:
            equivalence_transformer = EquivalenceTransformer(statement, self)
            equivalence_transformer.process()
            processed_rules = [equivalence_transformer.rule]

            if equivalence_transformer.aux_rule is not None:
                processed_rules.append(equivalence_transformer.aux_rule)
            return processed_rules

    def print_predicate_graph(self):
        print("\nInput Predicate "
              "Dependencies\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n")
        for predicate_head in self.predicate_adjacency_list.keys():
            dependency = " %s: " % predicate_head.__str__()

            for predicate_body in self.predicate_adjacency_list[predicate_head]:
                dependency = dependency + (" %s" % predicate_body.__str__())
            print(dependency)
        print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

    def print_input_statements(self):
        print("\nProgram Input\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n")
        for stm in self.input_statements:
            print(stm)
        print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

    def print_output_statements(self):
        print("\nProgram Output\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n")
        for stm in self.output_statements:
            print(stm)
        print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
