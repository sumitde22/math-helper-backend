from flask import Blueprint, jsonify, abort, request
# allows cursor to return data in dict format instead of tuple
from psycopg2.extras import RealDictCursor
# library for restricting endpoints to authenticated users and auto parsing/authenticating tokens
from flask_jwt_extended import jwt_required, current_user
from .db import get_db_connection
from json import loads
# library for parsing user algebraic inputs and determining symbolic equality
from sympy import parse_expr

# initalize blueprint to load problem handling route handlers onto
problems_blueprint = Blueprint('problems', __name__, url_prefix='/api/problems')

# procedure that determines which questions user should answer today and tracks them
# should be called during startup/login
def assign_daily_problems(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute('call assign_daily_questions(%s);', (user_id,))
    cursor.close()

# determine all problems that are assigned today and haven't been solved yet for given user
def get_problems_assigned_today(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT problem_set.* FROM daily_assignment INNER JOIN problem_set ON daily_assignment.problem_id = problem_set.id ' 
    'WHERE date=CURRENT_DATE AND user_id=%s AND solved=false ORDER BY problem_set.id;', (user_id,))
    todays_problems = cursor.fetchall()
    cursor.close()
    return todays_problems

# get user-agnostic problem info
def get_problems():
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT * FROM problem_set ORDER BY id;')
    problems = cursor.fetchall()
    cursor.close()
    return problems

# get problem info mixed with user's statistics for each problem
def get_problems_with_statistics(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT DISTINCT problem_set.*, '
    'COUNT(*) filter(where user_attempt_log.correct and user_attempt_log.user_id=%s) OVER (PARTITION BY user_attempt_log.problem_id) AS solved, '
    'COUNT(*) filter(where user_attempt_log.user_id=%s) OVER (PARTITION BY user_attempt_log.problem_id) AS attempts, '
    'MAX(attempt_date) filter(where user_attempt_log.correct and user_attempt_log.user_id=%s) OVER (PARTITION BY user_attempt_log.problem_id) AS most_recent_solved '
    'FROM problem_set LEFT JOIN user_attempt_log ON problem_set.id = user_attempt_log.problem_id ORDER BY problem_set.id;', (user_id, user_id, user_id))
    problems = cursor.fetchall()
    cursor.close()
    return problems

# get problem info based on id
def get_problem(problem_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT * FROM problem_set WHERE id=%s;', (problem_id,))
    problem = cursor.fetchone()
    cursor.close()
    return problem

# get problem info mixed with user's statistics for given problem
def get_problem_with_statistics(user_id, problem_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT DISTINCT problem_set.*, '
    'COUNT(*) filter(where user_attempt_log.correct and user_attempt_log.user_id=%s) OVER (PARTITION BY user_attempt_log.problem_id) AS solved, '
    'COUNT(*) filter(where user_attempt_log.user_id=%s) OVER (PARTITION BY user_attempt_log.problem_id) AS attempts, '
    'MAX(attempt_date) filter(where user_attempt_log.correct and user_attempt_log.user_id=%s) OVER (PARTITION BY user_attempt_log.problem_id) AS most_recent_solved '
    'FROM problem_set LEFT JOIN user_attempt_log ON problem_set.id = user_attempt_log.problem_id WHERE problem_set.id = %s;', (user_id, user_id, user_id, problem_id))
    problem = cursor.fetchone()
    cursor.close()
    return problem

# erase all attempts for given problem and user from history
def reset_problem(user_id, problem_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    # erase previous attempts, reset intervals for assignments, and assign first new attempt for tommorrow
    # see reset_problem_statistics in util.sql
    cursor.execute('call reset_problem_statistics(%s, %s);', (user_id, problem_id))
    cursor.close()

# insert problem attempt into db
# next daily attempt will be scheduled based on schedule_next_assignment trigger, see util.sql for definition
def log_response(user_id, problem_id, correct, response):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute('INSERT INTO user_attempt_log(user_id, problem_id, response, correct, attempt_date) VALUES (%s, %s, %s, %s, CURRENT_DATE);', (user_id, problem_id, response, correct))
    cursor.close()

# endpoint to process a user attempt to solve a problem
@problems_blueprint.route('/solve/<int:problem_id>', methods=['POST'])
@jwt_required()
def solve_problem(problem_id):
    user_id = current_user['id']
    payload = request.get_json()
    answer = payload['answer']

    # send error if problem id doesn't exist
    # (frontend handles error page)
    problem = get_problem(problem_id)
    if problem == None:
        abort(404, f'Problem with id {problem_id} does not exist')

    # load algebraic assumptions about symbols used in problem
    # e.g. assuming x is real or y is an integer
    sympy_assumptions = {} if problem['assumptions_json'] == None else loads(problem['assumptions_json'])
    for key in sympy_assumptions:
        sympy_assumptions[key] = parse_expr(sympy_assumptions[key])

    # try to parse user response algebraically, throw error if sympy cannot create valid expression
    try:
        answer_expression = parse_expr(answer, sympy_assumptions)
    except Exception:
        abort(400, f'Answer did not follow correct format and could not be parsed. Please resubmit')

    # process 1: check to see if user response is mathematically equal to solved version of problem

    problem_expression = parse_expr(problem['sympy_rep'], sympy_assumptions, evaluate=False)
    # make sure user provides some simplification of problem and doesn't just resubmit problem
    if problem_expression == answer_expression:
        abort(400, f'Answer matches problem symbolically. Please answer with simplified version of problem')
    
    # if problem is derivative/integral, execute operation
    if problem['expression_type'] == 'derivative' or problem['expression_type'] == 'integral':
        problem_expression = problem_expression.doit()

    # simplify both problem and user response as much as possible
    sympy_user_comparison = (problem_expression - answer_expression).simplify()
    while sympy_user_comparison != sympy_user_comparison.simplify():
        sympy_user_comparison = sympy_user_comparison.simplify()
    # if user submits answer that is mathematically equal to problem, log it as correct and inform user that it is correct
    if sympy_user_comparison == 0:
        # logging the response will trigger another function that will calculate when to next assign this problem
        # see schedule_next_assignment in util.sql
        log_response(user_id, problem_id, True, answer)
        return {'sample_solution': problem['sample_solution_latex'], 'correct': True}

    # process 2: if sympy doesn't determine problem and user response to be mathematically equivalent,
    # check to see if user response is equal to a sample solution for that problem
    solution_expression = parse_expr(problem['sample_solution_sympy'], sympy_assumptions)
    # simplify both solution and user response as much as possible
    sample_solution_user_comparison = (solution_expression - answer_expression).simplify()
    while sample_solution_user_comparison != sample_solution_user_comparison.simplify():
        sympy_user_comparison = sympy_user_comparison.simplify()
    # if user submits answer that is mathematically equal to sample solution, log it as correct and inform user that it is correct
    if sample_solution_user_comparison == 0:
        # logging the response will trigger another function that will calculate when to next assign this problem
        # see schedule_next_assignment in util.sql
        log_response(user_id, problem_id, True, answer)
        return {'sample_solution': problem['sample_solution_latex'], 'correct': True}

    # process 3: if response is not equal to solved problem or solution, the user is informed that it is incorrect and given a sample solution
    # response is logged
    log_response(user_id, problem_id, False, answer)
    return {'sample_solution': problem['sample_solution_latex'], 'correct': False}

# endpoint to return a given problem's info
@problems_blueprint.route('/<int:problem_id>', methods=['GET'])
@jwt_required(optional=True)
def get_problem_by_id(problem_id):
    # if no token sent, just send the math info about the problem
    if current_user == None:
        problem = get_problem(problem_id)
        # send error if problem doesn't exist
        if problem == None:
            abort(404, f'Problem with id {problem_id} does not exist')
        else:
            return problem
    # if token sent, also send user's statistics for problem
    else:
        user_id = current_user['id']
        problem = get_problem_with_statistics(user_id, problem_id)
        if problem == None:
            abort(404, f'Problem with id {problem_id} does not exist')
        else:
            return problem

# endpoint that allows user to modify problem status
@problems_blueprint.route('/<int:problem_id>', methods=['PUT'])
@jwt_required()
def modify_problem_status(problem_id):
    user_id = current_user['id']
    payload = request.get_json()
    # the only thing that can be modified is "resetting" a problem to erase previous attempts
    # this is achieved by sending a reset tag in json
    try:
        should_reset = payload['reset']
    except:
        should_reset = False
    
    # send error if problem doesn't exist
    problem = get_problem(problem_id)
    if problem == None:
        abort(404, f'Problem with id {problem_id} does not exist')
    
    # else, reset problem by erasing previous user attempts and assigning the first new attempt for tommorrow
    if should_reset: 
        reset_problem(user_id, problem_id)
        return {'msg': f'Problem with id {problem_id} reset'}
    else:
        return {'msg': 'No changes made'}

# endpoint that returns the daily problems remaining for given user
@problems_blueprint.route('/daily', methods=['GET'])
@jwt_required()
def get_daily_problems():
    user_id = current_user['id']

    daily_problems = get_problems_assigned_today(user_id)
    return jsonify(daily_problems)

# endpoint that returns all problem info
@problems_blueprint.route('/', methods=['GET'])
@jwt_required(optional=True)
def get_all_problems():
    # if no/invalid token sent, simply send the math info for all problems
    if current_user == None:
        problems = get_problems()
        return jsonify(problems)
    # if valid token sent, send the user statistics for each problem along with the math info
    else:
        user_id = current_user['id']
        problems = get_problems_with_statistics(user_id)
        return jsonify(problems)

