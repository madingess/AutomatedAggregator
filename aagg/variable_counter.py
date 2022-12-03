import clingo


def convert_binary_op_to_var_plus_int(term):
    """
        Determines whether a BinaryOperation defined by term can be
            converted to the form 'var + a' where a is an integer
        Outputs var and a if possible; otherwise var, a = None, None
    """
    # Check if term is simply a variable; return var, a=0 if so
    if term.type == clingo.ast.ASTType.Variable:
        return term, 0

    # Otherwise ensure term is a binary operation
    if term.type == clingo.ast.ASTType.BinaryOperation:
        # Ensure operator is Plus or Minus
        if term['operator'] == clingo.ast.BinaryOperator.Plus or \
                term['operator'] == clingo.ast.BinaryOperator.Minus:
            # Get multiplier for right term, if it is a symbol
            if term['operator'] == clingo.ast.BinaryOperator.Plus:
                multiplier = 1
            else:
                multiplier = -1

            # Get variable and integer value times multiplier
            if term['left'].type == clingo.ast.ASTType.Variable and \
                    term['right'].type == clingo.ast.ASTType.Symbol:
                value = int(str(term['right']['symbol']))  # Can this cause errors?
                return term['left'], (value * multiplier)

            # Must also ensure variable is not being subtracted
            elif term['left'].type == clingo.ast.ASTType.Symbol and \
                    term['right'].type == clingo.ast.ASTType.Variable and \
                    term['operator'] == clingo.ast.BinaryOperator.Plus:
                value = int(str(term['left']['symbol']))  # Can this cause errors?
                return term['right'], value

    # If no usable binary operation conversion found, return failure
    return None, None


def convert_binary_op_to_vars(term1, term2, comparison):
    """
        Handles cases of BinaryOperations given to a comparison which
            may still be candidate for rewriting
        Currently handles only binary operations between variables 
            and symbols
    """
    var1, int1 = convert_binary_op_to_var_plus_int(term1)  # Returns None, None if no conversion found
    var2, int2 = convert_binary_op_to_var_plus_int(term2)

    candidate = False  # Flag to track whether a valid conversion was found

    if var1 and var2:
        diff = int2 - int1

        # Cases defined in README
        if diff == 0:
            if comparison == clingo.ast.ComparisonOperator.GreaterThan or \
                    comparison == clingo.ast.ComparisonOperator.LessThan or \
                    comparison == clingo.ast.ComparisonOperator.NotEqual:
                candidate = True
        elif diff == -1 and \
                comparison == clingo.ast.ComparisonOperator.LessEqual:
            comparison = clingo.ast.ComparisonOperator.LessThan
            candidate = True
        elif diff == 1 and \
                comparison == clingo.ast.ComparisonOperator.GreaterEqual:
            comparison = clingo.ast.ComparisonOperator.GreaterThan
            candidate = True

    # if no cases met, return None, None, None to indicate inelegibility for conversion
    if candidate:
        return var1, var2, comparison
    else:
        return None, None, None  # Failure indicator


class VariableCounter:
    """This class is used to track how much a variable is used within a rule"""

    def __init__(self):
        self.variable_count = {}
        self.comparison_variables = {'greatThan': {}, 'notEqual': {}}

    def increment(self, var_name):
        """Increments the variable counter"""
        if var_name not in self.variable_count:
            self.variable_count[var_name] = 0

        self.variable_count[var_name] += 1

    def mark_comparison(self, var1, var2, comparison):
        """    
            Marks the variables as being used in a (non-Equal) 
                comparison literal and ensures the variable is not a constant
        """
        var1, var2, comparison = convert_binary_op_to_vars(var1, var2, comparison)

        if var1 and var2:  # Var1 and Var2 not None (indicates non-candidate comparison)
            var1 = var1.name
            var2 = var2.name
            if comparison == clingo.ast.ComparisonOperator.NotEqual:  
                # Make notEqual dictionary entry of var1: [var2] and var2: [var1]
                if self.comparison_variables['notEqual'].has_key(var1):
                    self.comparison_variables['notEqual'][var1].append(var2)
                else:
                    self.comparison_variables['notEqual'][var1] = [var2]
                if self.comparison_variables['notEqual'].has_key(var2):
                    self.comparison_variables['notEqual'][var2].append(var1)
                else:
                    self.comparison_variables['notEqual'][var2] = [var1]

            elif comparison == clingo.ast.ComparisonOperator.GreaterThan:  
                # Make lessThan dictionary entry of var1: [var2]
                if self.comparison_variables['greatThan'].has_key(var1):
                    self.comparison_variables['greatThan'][var1].append(var2)
                else:
                    self.comparison_variables['greatThan'][var1] = [var2]

            elif comparison == clingo.ast.ComparisonOperator.LessThan:  
                # Make lessThan dictionary entry of var1: [var2]
                if self.comparison_variables['greatThan'].has_key(var2):
                    self.comparison_variables['greatThan'][var2].append(var1)
                else:
                    self.comparison_variables['greatThan'][var2] = [var1]

    def longest_path_finder(self, comp_type, seen_set, current_var):
        """
            Given a comparison type, set of variables already seen,
                and our current variable
            Return variables in longest continuous path of comparisons
                between variables, recursively exploring each path in 
                the comparison 'tree' of given comparison type
        """
        # First check special cases for each comparison type
        if comp_type == 'greatThan':
            # Abort path if a cycle is found in greatThan case, for this means nonsense logic
            if self.comparison_variables[comp_type].has_key(current_var):
                for nextVar in self.comparison_variables[comp_type][current_var]:
                    if nextVar in seen_set:  # if we've seen a var which currVar is greater than...
                        return []

        elif comp_type == 'notEqual':
            # Simpy return current path if current variable does not 
            #  have a comparison with all other seen variables, in notEqual case
            for seenVar in seen_set:
                if current_var not in self.comparison_variables[comp_type][seenVar]:
                    return list(seen_set)

        # Add current variable to the path and the set of seen variables
        seen_set.add(current_var)

        # Get set of variables having a comparison with the current variable
        if self.comparison_variables[comp_type].has_key(current_var):  # error checking
            nextVars = set([nextVar for nextVar in self.comparison_variables[comp_type][current_var]])
            operating_set = nextVars
        else:
            operating_set = set()

        # Subtract variables already seen from the next path step candidates
        operating_set = operating_set - seen_set

        if len(operating_set) == 0:
            # Return if no more paths
            return list(seen_set)
        else:
            # get longest path from this node for each var it has comparisons with
            path_sets = []
            for var in operating_set:
                path_sets.append(self.longest_path_finder(comp_type, seen_set.copy(), var))

            # return longest of paths
            greatest_path = []
            for path in path_sets:
                if len(path) > len(greatest_path):
                    greatest_path = path
            return greatest_path

    def get_counting_variables(self):
        """
            Gets potential counting variables using comparisons by 
                finding the longest consecutive comparison path out of 
                both types of comparisons
            This function is called in EquivalenceTransformer.rewritable
        """
        # For both comparison types, find the longest comparison path starting from each variable
        longest_paths = []
        for comparison_type in self.comparison_variables.keys():
            for var in self.comparison_variables[comparison_type].keys():
                longest_path = self.longest_path_finder(comparison_type, set(), var)
                longest_paths.append(longest_path)

        # Return the subset of counting_vars_combs with greatest length    
        # This works non-deterministically, but if we have overlapping yet non-equal
        #  possibilities, the rule will note be rewritten anyway
        greatest = []
        for path in longest_paths:
            if len(path) > len(greatest):
                greatest = path
        return greatest
