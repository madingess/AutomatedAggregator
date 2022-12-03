import clingo
import constants
from tree_data import TreeData
from variable_counter import VariableCounter
from ast_visitor import ASTCopier
from predicate import Predicate, predicate_dependency


def get_function_counting_literals(rule, counting_vars):
    """
        Gets and verifies counting literals of functions from the rule
        Returns counting_literals, if any
    """
    # Get potential counting functions i.e.:
    #  every Literal in body with child_keys ['atom'] and positive (none) sign
    #  child ['atom'] having type SymbolicAtom with child keys ['term']
    #  child ['term'] having type Function with child keys ['arguments']
    #   where ['arguments'] has one or more variables
    potential_literals = []
    # We are guaranteed to have a body if we have counting variables
    for body_literal in rule['body']:
        if body_literal.child_keys == ['atom'] and \
                body_literal.sign != clingo.ast.Sign.Negation and \
                body_literal.sign != clingo.ast.Sign.DoubleNegation:
            if body_literal['atom'].type == clingo.ast.ASTType.SymbolicAtom and \
                    body_literal['atom'].child_keys == ['term']:
                if body_literal['atom']['term'].type == clingo.ast.ASTType.Function and \
                        body_literal['atom']['term'].child_keys == ['arguments'] and \
                        len(body_literal['atom']['term']['arguments']) > 0:
                    potential_literals.append(body_literal)

    # Check exactly one counting variable appears in each potential function
    for lit in potential_literals:
        occurrences = 0
        for var in counting_vars:
            for lit_var in lit['atom']['term']['arguments']:
                # Comparing string representations avoids AttributeErrors
                if str(lit_var) == str(var):
                    occurrences = occurrences + 1
        if occurrences != 1:
            potential_literals.remove(lit)
    if len(potential_literals) < 1:
        return []

    # Check that all potential functions are identical and have the same length
    for lit1 in potential_literals:
        func1 = str(lit1).split("(")[0]
        func1_arg_len = len(lit1['atom']['term']['arguments'])
        for lit2 in potential_literals:
            # This loop also compares each literal to itself and repeats
            #     comparisons, but this is trivial
            func2 = str(lit2).split("(")[0]
            func2_arg_len = len(lit2['atom']['term']['arguments'])
            if func1 != func2 or func1_arg_len != func2_arg_len:
                return []

    # Get the position of the counting variable in each of the potential
    #      counting literals
    position = -1
    lit_args = potential_literals[0]['atom']['term']['arguments']
    for var in counting_vars:
        if position != -1:
            break

        for i in range(len(lit_args)):
            if str(var) == str(lit_args[i]):
                position = i
                break

    # Then use that position to verify the location of the counting
    #    variable is the same for the for all the potential literals
    for lit in potential_literals:
        lit_var = lit['atom']['term']['arguments'][position]
        positional_occurrence = False
        for countVar in counting_vars:
            if str(lit_var) == str(countVar):
                positional_occurrence = True
        if not positional_occurrence:
            return []

    # Verify the non-counting variables are identical in all potential literals
    non_count_args = potential_literals[0]['atom']['term']['arguments'][:]
    non_count_args.remove(non_count_args[position])
    for otherLit in potential_literals:

        lit_args = otherLit['atom']['term']['arguments'][:]
        lit_args.remove(lit_args[position])

        if cmp(non_count_args, lit_args) != 0:  # returns 0 for equality
            return []

    return potential_literals


def get_comparison_counting_literals(rule, counting_vars):
    """Gets and verifies counting literals of comparisons from the rule"""
    counting_literals = []

    for body_lit in rule['body']:

        # Literal must not be negated and must contain a comparison
        # There's no need to check 'not/'not not' for comparisons as clingo
        #     auto-rewrites this during parsing
        if body_lit.type == clingo.ast.ASTType.Literal and \
                body_lit.child_keys == ['atom'] and \
                body_lit['atom'].type == clingo.ast.ASTType.Comparison and \
                body_lit['atom']['comparison'] != clingo.ast.ComparisonOperator.Equal:

            # Left side of comparison must contain a counting variable
            left = None
            if str(body_lit['atom']['left']) in counting_vars:
                left = body_lit['atom']['left']

            # Handle cases where the left side of the comparison
            #    take one of the following forms:
            #         counting_variable {+,-} integer
            #        integer + counting_variable
            elif body_lit['atom']['left'].type == clingo.ast.ASTType.BinaryOperation:
                if str(body_lit['atom']['left']['left']) in counting_vars and \
                        body_lit['atom']['left']['right'].type == clingo.ast.ASTType.Symbol:
                    left = body_lit['atom']['left']['left']
                elif str(body_lit['atom']['left']['right']) in counting_vars and \
                        body_lit['atom']['left']['left'].type == clingo.ast.ASTType.Symbol and \
                        body_lit['atom']['left']['operator'] == clingo.ast.BinaryOperator.Plus:
                    left = body_lit['atom']['left']['right']

            # Right side of comparison must contain a counting variable
            right = None
            if str(body_lit['atom']['right']) in counting_vars:
                right = body_lit['atom']['right']

            # Right side may also take an alternative form
            elif body_lit['atom']['right'].type == clingo.ast.ASTType.BinaryOperation:
                if str(body_lit['atom']['right']['left']) in counting_vars and \
                        body_lit['atom']['right']['right'].type == clingo.ast.ASTType.Symbol:
                    right = body_lit['atom']['right']['left']
                elif str(body_lit['atom']['right']['right']) in counting_vars and \
                        body_lit['atom']['right']['left'].type == clingo.ast.ASTType.Symbol and \
                        body_lit['atom']['right']['operator'] == clingo.ast.BinaryOperator.Plus:
                    right = body_lit['atom']['right']['right']

            # If counting variables are found for both sides of the comparison,
            #     add it to the list of comparison counting literals
            if right is not None and left is not None:
                counting_literals.append(body_lit)

    return counting_literals


def get_counting_function_from_literals(counting_literals):
    """
        Given counting literals of functions and comparisons
        Returns first counting function encountered

        Will always find a counting function, as the counting
            literals are verified by other functions
    """
    for lit in counting_literals:
        if lit['atom'].type == clingo.ast.ASTType.SymbolicAtom and \
                lit['atom'].child_keys == ['term'] and \
                'name' in lit['atom']['term'].keys():
            return lit['atom']['term']

    print("Error: Cannot get counting function from counting literals")


def get_counting_function_args(counting_function, counting_vars):
    """
        Given a counting function and counting var
        Returns its arguments, the counting variable used in it,
            as well its set of arguments with the counting variable
            replaced by the anonymous variable

        Will always find a counting function, as the counting
            literals are verified by other functions
    """
    reg_args = counting_function['arguments'][:]
    anon_args = []
    ret_var = 'Error'
    for argVar in reg_args:
        if str(argVar) in counting_vars:
            anon_args.append(clingo.ast.Variable(constants.LOCATION, '_'))
            ret_var = argVar
        else:
            anon_args.append(argVar)

    return reg_args, ret_var, anon_args


class EquivalenceTransformer:
    """
        This class is the basis for detecting and performing equivalence
        Every rule has its own EquivalenceTransformer
    """

    def __init__(self, rule, base_transformer):
        self.rule = rule
        self.base_transformer = base_transformer

        self.variable_counter = VariableCounter()
        self.aux_rule = None
        self.aux_predicate = None
        self.rule_functions = []
        self.counting_literals = []
        self.counting_variables = []

    def process(self):
        """
            Processes a rule to perform rewriting
        """
        if self.base_transformer.Setting.DEBUG:
            print "equivalence_transformer: processing rule:  %s" % self.rule

        rule_original = ASTCopier().deep_copy(self.rule)  # For resetting rule if rewrite is denied by user
        self.rule = self.explore(self.rule)  # Garners information for rewritability checking
        equiv_output_forms = self.rewritable_forms()  # Determines available output forms for this rule

        if self.base_transformer.Setting.DEBUG:
            print "equivalence_transformer: valid output forms:  " + str(equiv_output_forms)

        if self.base_transformer.Setting.AGGR_FORM in equiv_output_forms:
            self.rewrite_rule()
            self.print_rewrite(rule_original)
            self.confirm_rewrite(rule_original)  # Undoes rewriting if user denies rewrite

        elif len(equiv_output_forms) > 0:
            # Equivalent output forms exist, but not for the requested form.
            # Currently this only occurs for forms (2) and (3) because a cyclic dependency exists
            print "Warning! Rule:  %s\n\nCould not be rewritten due to a cyclic dependency." % rule_original

    def explore(self, x, data=TreeData()):
        """
            Recursively traverse AST of the rule.
            Record encountered comparisons and functions for use in
                checking for potential rewritings of the rule
        """
        if isinstance(x, clingo.ast.AST):
            # Record non-equality comparisons for use in rewritability checking
            if x.type == clingo.ast.ASTType.Comparison:
                if x['comparison'] != clingo.ast.ComparisonOperator.Equal:
                    self.variable_counter.mark_comparison(x['left'], x['right'], x['comparison'])

            # Record body functions for use in rewritability checking
            elif x.type == clingo.ast.ASTType.Function:
                if not data.head:
                    self.rule_functions.append(x)

            return self.explore_children(x, data)

        elif isinstance(x, list):
            return [self.explore(y, data) for y in x]
        elif x is None:
            return x
        else:
            raise TypeError("unexpected type")

    def explore_children(self, x, data=TreeData()):
        for key in x.child_keys:
            attr = self.explore(x[key], TreeData(data.head or key == "head"))
            x[key] = attr
        return x

    def print_rewrite(self, rule_before_rewriting):
        """
            Prints to console the rule before and after rewriting, and
                an auxiliary rule, if any
        """
        print "\nBefore rewriting: %s" % rule_before_rewriting
        print "After rewriting:  %s\n" % self.rule
        if self.aux_rule is not None:
            print "\t(Adds Auxiliary Rule)  %s\n" % self.aux_rule
            print "Warning: This is not strongly equivalent for programs with " \
                  "rules or facts containing the predicate:  %s\n" % \
                  self.aux_predicate

    def confirm_rewrite(self, rule_before_rewriting):
        """
            Given the rule before rewrite is performed.
            If rewriting is not confirmed by cli, prompts the user to
                confirm the proposed rewrite and acts accordingly.
            Otherwise the rule is automatically confirmed.
        """
        if not self.base_transformer.Setting.CONFIRM_REWRITE:
            option = raw_input("Confirm rewriting (y/n) ").lower()
            if option == "n" or option == "no":
                print("Rule rewriting denied.\n")
                self.aux_rule = None
                self.rule = rule_before_rewriting
                self.base_transformer.new_predicates.remove(self.aux_predicate)
            else:
                print("Rule rewriting confirmed.\n")

    def counting_vars_used_elsewhere(self, check_rule, counting_literals, counting_vars):
        """
            Recursive wrapper for counting_vars_not_used_elsewhere_helper.
            Checks if any of the given counting variable occurs within 
                the given rule, not including the counting_literals
            Returns true if an occurrence is found; false otherwise
        """
        for lit in counting_literals:
            check_rule['body'].remove(lit)

        return self.counting_vars_used_elsewhere_helper(check_rule, counting_vars)

    def counting_vars_used_elsewhere_helper(self, node, counting_vars):
        """
            Recursively check children of all nodes in AST for 'arguments'
                child key, then check 'arguments' for counting variables
            Returns False if no occurrence
        """
        if isinstance(node, clingo.ast.AST):

            if node.type == clingo.ast.ASTType.Variable:
                if str(node) in counting_vars:
                    return True

            # If a node does not have arguments but has children, check children
            elif len(node.child_keys) > 0:
                ret = False
                for key in node.child_keys:
                    ret = ret or self.counting_vars_used_elsewhere_helper(node[key], counting_vars)
                return ret

        elif isinstance(node, list):
            ret = False
            for entry in node:
                ret = ret or self.counting_vars_used_elsewhere_helper(entry, counting_vars)
            return ret

        else:
            raise TypeError("unexpected type")

    def circular_dependencies(self, counting_predicate):
        """
            Certain output forms for a rewriting are equivalent only if the
                predicates in the body of the input rule are not dependent 
                on the predicates in the head of the rule.
                (i.e. the rule forms no circular dependencies)
            A predicate x 'depends' on another predicate y if x is defined in
                a rule in which y is in the body. Ex:
                        "x(A) :- y(A)."
                However, the dependency property is transitive across predicates.
            Given a predicate, the counting predicate.
            Returns True if the counting predicate depends on any
                predicate in the head of the rule
        """
        for head_predicate in self.get_head_predicates():
            if predicate_dependency(
                    self.base_transformer.predicate_adjacency_list,
                    counting_predicate,
                    head_predicate):
                return True

        return False

    def get_head_predicates(self):
        """
            Uses the ASTPredicateMapper to get the predicate map for the 
                current rule. (slightly overkill)
            From the predicate map, returns a list of the predicates in 
                the head of the current rule
        """
        # generate a new map from the current rule
        self.base_transformer.predicate_mapper.clear_map()
        self.base_transformer.predicate_mapper.map_rule_predicates(self.rule)
        predicate_map = self.base_transformer.predicate_mapper.predicate_map

        # head predicates will be the only predicates with dependencies
        return predicate_map.keys()

    def rewritable_forms(self):
        """
            Checks if the rule meets conditions to be rewritable by 
                aggregate equivalence for the given form.
            Forms (2) and (3) must satisfy the additional condition that 
                the counting predicate does not depend on the head predicates
            Returns the list of valid output forms for potential rewriting
        """
        counting_vars = self.variable_counter.get_counting_variables()
        if len(counting_vars) < 2:
            return []

        check_rule = ASTCopier().deep_copy(self.rule)

        counting_literals = get_function_counting_literals(check_rule, counting_vars)
        counting_literals += get_comparison_counting_literals(check_rule, counting_vars)
        if len(counting_literals) < 3:  # Must be at least two counting functions and one comparison
            return []

        if self.counting_vars_used_elsewhere(check_rule, counting_literals, counting_vars):
            return []

        counting_function = get_counting_function_from_literals(counting_literals)
        counting_predicate = Predicate(counting_function['name'], len(counting_function['arguments']))
        if self.circular_dependencies(counting_predicate):
            valid_forms = [constants.AGGR_FORM1]
        else:
            valid_forms = [constants.AGGR_FORM1, constants.AGGR_FORM2, constants.AGGR_FORM3]

        # record counting literal and variable information for performing rewriting later
        self.counting_literals = counting_literals
        self.counting_variables = counting_vars
        return valid_forms

    def get_projection_predicate(self, counting_function, counting_var, arity):
        """
            Creates a predicate for a new function with a name 
                following the pattern:
                    COUNTINGFUNCTIONNAME_proj_COUNTINGVAR#
                where # is initially empty.
            If a collision occurs with other function names in the current
                operating file, then # is 1. If there is still a 
                collision, # is incremented until there is none
            Returns the new projection predicate
        """
        new_predicate = Predicate(counting_function['name'] + '_project_' + str(counting_var), arity)
        iteration = 1
        while new_predicate in self.base_transformer.in_predicates or \
                new_predicate in self.base_transformer.new_predicates:
            new_predicate.name = new_predicate.name + str(iteration)
            iteration += 1

        self.base_transformer.new_predicates.add(new_predicate)
        return new_predicate

    def make_auxiliary_definition(self, counting_function):
        """
            Given the counting function
            Return a literal of the counting function with the counting 
                variable projected out, and a rule which defines the 
                auxiliary term
            When this is called, we are certain to have a counting
                variable within the given counting_function
        """

        # Get the functions arguments, less its counting variable
        projected_args = counting_function['arguments'][:]
        for counting_var in self.counting_variables:
            for function_var in projected_args:
                if counting_var == str(function_var):
                    projected_args.remove(function_var)
                    break

        projection_predicate = self.get_projection_predicate(counting_function, counting_var, len(projected_args))

        # Make Function and Literal with projected arguments and name
        aux_function = clingo.ast.Function(constants.LOCATION,
                                           projection_predicate.name,
                                           projected_args,
                                           False)
        aux_literal = clingo.ast.Literal(constants.LOCATION,
                                         clingo.ast.Sign.NoSign,
                                         clingo.ast.SymbolicAtom(aux_function))

        # Make rule defining the auxiliary function
        counting_literal = clingo.ast.Literal(constants.LOCATION,
                                              clingo.ast.Sign.NoSign,
                                              clingo.ast.SymbolicAtom(counting_function))
        aux_rule = clingo.ast.Rule(constants.LOCATION, aux_literal, [counting_literal])

        return projection_predicate, aux_literal, aux_rule

    def rewrite_rule(self):
        """Performs aggregate rewriting on the given rule"""
        for lit in self.counting_literals:
            self.rule['body'].remove(lit)

        counting_function = get_counting_function_from_literals(self.counting_literals)
        rewritten_literals = self.create_aggregate_literals(counting_function)

        if len(counting_function['arguments']) > 1:  # Projection needed if function has multiple arguments
            aux_predicate, aux_lit, aux_rule = self.make_auxiliary_definition(counting_function)
            self.aux_predicate = aux_predicate
            self.aux_rule = aux_rule

            rewritten_literals.append(aux_lit)

        self.rule['body'] += rewritten_literals

    def create_aggregate_literals(self, counting_function):
        """
            Given a function.
            Creates counting aggregate literal(s) of the user
                specified form with the given counting function
                
            Returns aggregate literal(s) as a list
        """
        function_name = counting_function['name']
        regular_args, counting_var, anonymous_args = get_counting_function_args(counting_function,
                                                                                self.counting_variables)

        # Create aggregate elements having the form:
        #    "F(_,Y) : F(_,Y)"    if using anonymous variable, for proper grounding
        #    "X : F(X,Y)"         otherwise
        if self.base_transformer.Setting.USE_ANON:
            rewritten_function = clingo.ast.Function(constants.LOCATION, function_name, anonymous_args, False)
            rewritten_literal = clingo.ast.Literal(constants.LOCATION,
                                                   clingo.ast.Sign.NoSign,
                                                   clingo.ast.SymbolicAtom(rewritten_function))
            aggregate_components = [clingo.ast.ConditionalLiteral(constants.LOCATION,
                                                                  rewritten_literal,
                                                                  [rewritten_literal])]

        else:
            rewritten_function = clingo.ast.Function(constants.LOCATION, function_name, regular_args, False)
            rewritten_lit = clingo.ast.Literal(constants.LOCATION,
                                               clingo.ast.Sign.NoSign,
                                               clingo.ast.SymbolicAtom(rewritten_function))
            aggregate_components = [clingo.ast.BodyAggregateElement([counting_var], [rewritten_lit])]

        num_counting_vars = len(self.counting_variables)  # Let b be the number of counting variables

        # Make aggregate of one of three output forms, as specified by the user
        if self.base_transformer.Setting.AGGR_FORM == 3:
            # Form:  not b-1={}, not b-2={}, ..., not 0={}

            aggr_literals = []
            for i in range(1, num_counting_vars + 1):  # range 1..b

                aggr_left_guard = clingo.ast.AggregateGuard(clingo.ast.ComparisonOperator.Equal,
                                                            clingo.ast.Symbol(constants.LOCATION,
                                                                              num_counting_vars - i))
                aggr_right_guard = None

                # Use specified aggregate inside form (see above)
                if self.base_transformer.Setting.USE_ANON:
                    rwn_aggr = clingo.ast.Aggregate(constants.LOCATION,
                                                    aggr_left_guard,
                                                    aggregate_components,
                                                    aggr_right_guard)
                else:
                    rwn_aggr = clingo.ast.BodyAggregate(constants.LOCATION,
                                                        aggr_left_guard,
                                                        clingo.ast.AggregateFunction.Count,
                                                        aggregate_components,
                                                        aggr_right_guard)

                aggr_literal = clingo.ast.Literal(constants.LOCATION, clingo.ast.Sign.Negation, rwn_aggr)
                aggr_literals.append(aggr_literal)

        elif self.base_transformer.Setting.AGGR_FORM == 2:
            # Form:  not {} < b

            aggr_left_guard = None
            aggr_right_guard = clingo.ast.AggregateGuard(clingo.ast.ComparisonOperator.LessThan,
                                                         clingo.ast.Symbol(constants.LOCATION, num_counting_vars))

            if self.base_transformer.Setting.USE_ANON:
                rwn_aggr = clingo.ast.Aggregate(constants.LOCATION,
                                                aggr_left_guard,
                                                aggregate_components,
                                                aggr_right_guard)
            else:
                rwn_aggr = clingo.ast.BodyAggregate(constants.LOCATION,
                                                    aggr_left_guard,
                                                    clingo.ast.AggregateFunction.Count,
                                                    aggregate_components,
                                                    aggr_right_guard)

            aggr_literals = [clingo.ast.Literal(constants.LOCATION, clingo.ast.Sign.Negation, rwn_aggr)]

        else:
            # [Default case] Form:  b <= {}

            aggr_left_guard = clingo.ast.AggregateGuard(clingo.ast.ComparisonOperator.LessEqual,
                                                        clingo.ast.Symbol(constants.LOCATION, num_counting_vars))
            aggr_right_guard = None

            if self.base_transformer.Setting.USE_ANON:
                rwn_aggr = clingo.ast.Aggregate(constants.LOCATION,
                                                aggr_left_guard,
                                                aggregate_components,
                                                aggr_right_guard)
            else:
                rwn_aggr = clingo.ast.BodyAggregate(constants.LOCATION,
                                                    aggr_left_guard,
                                                    clingo.ast.AggregateFunction.Count,
                                                    aggregate_components,
                                                    aggr_right_guard)

            aggr_literals = [clingo.ast.Literal(constants.LOCATION, clingo.ast.Sign.NoSign, rwn_aggr)]

        return aggr_literals
