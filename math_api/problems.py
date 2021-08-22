from flask import Blueprint, jsonify, abort, request
from psycopg2.extras import RealDictCursor
from flask_jwt_extended import jwt_required, current_user
from .db import get_db_connection
import json
from sympy import parse_expr

problems_blueprint = Blueprint('problems', __name__, url_prefix='/api/problems')

def assign_daily_problems(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute('call assign_daily_questions(%s);', (user_id,))
    cursor.close()

def get_problems_assigned_today(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT problem_set.* FROM daily_assignment INNER JOIN problem_set ON daily_assignment.problem_id = problem_set.id ' 
    'WHERE date=CURRENT_DATE AND user_id=%s AND solved=false ORDER BY problem_set.id;', (user_id,))
    todays_problems = cursor.fetchall()
    cursor.close()
    return todays_problems

def get_problems():
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT * FROM problem_set ORDER BY id;')
    problems = cursor.fetchall()
    cursor.close()
    return problems

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

def get_problem(problem_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT * FROM problem_set WHERE id=%s;', (problem_id,))
    problem = cursor.fetchone()
    cursor.close()
    return problem

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

def reset_problem(user_id, problem_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute('call reset_problem_statistics(%s, %s);', (user_id, problem_id))
    cursor.close()

def log_response(user_id, problem_id, correct, response):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute('INSERT INTO user_attempt_log(user_id, problem_id, response, correct, attempt_date) VALUES (%s, %s, %s, %s, CURRENT_DATE);', (user_id, problem_id, response, correct))
    cursor.close()

@problems_blueprint.route('/solve/<int:problem_id>', methods=['POST'])
@jwt_required()
def solve_problem(problem_id):
    user_id = current_user['id']
    payload = request.get_json()
    answer = payload['answer']

    problem = get_problem(problem_id)
    if problem == None:
        abort(404, f'Problem with id {problem_id} does not exist')

    sympy_assumptions = {} if problem['assumptions_json'] == None else json.loads(problem['assumptions_json'])
    for key in sympy_assumptions:
        sympy_assumptions[key] = parse_expr(sympy_assumptions[key])

    try:
        answer_expression = parse_expr(answer, sympy_assumptions)
    except Exception:
        abort(400, f'Answer did not follow correct format and could not be parsed. Please resubmit')


    problem_expression = parse_expr(problem['sympy_rep'], sympy_assumptions, evaluate=False)
    solution_expression = parse_expr(problem['sample_solution_sympy'], sympy_assumptions)
    if problem_expression == answer_expression:
        abort(400, f'Answer matches problem symbolically. Please answer with simplified version of problem')
    
    if problem['expression_type'] == 'derivative' or problem['expression_type'] == 'integral':
        problem_expression = problem_expression.doit()

    sympy_user_comparison = (problem_expression - answer_expression).simplify()
    while sympy_user_comparison != sympy_user_comparison.simplify():
        sympy_user_comparison = sympy_user_comparison.simplify()
    if sympy_user_comparison == 0:
        log_response(user_id, problem_id, True, answer)
        return {'sample_solution': problem['sample_solution_latex'], 'correct': True}

    sample_solution_user_comparison = (solution_expression - answer_expression).simplify()
    while sample_solution_user_comparison != sample_solution_user_comparison.simplify():
        sympy_user_comparison = sympy_user_comparison.simplify()
    if sample_solution_user_comparison == 0:
        log_response(user_id, problem_id, True, answer)
        return {'sample_solution': problem['sample_solution_latex'], 'correct': True}

    log_response(user_id, problem_id, False, answer)
    return {'sample_solution': problem['sample_solution_latex'], 'correct': False}

@problems_blueprint.route('/<int:problem_id>', methods=['GET'])
@jwt_required(optional=True)
def get_problem_by_id(problem_id):
    if current_user == None:
        problem = get_problem(problem_id)
        if problem == None:
            abort(404, f'Problem with id {problem_id} does not exist')
        else:
            return problem
    else:
        user_id = current_user['id']
        problem = get_problem_with_statistics(user_id, problem_id)
        if problem == None:
            abort(404, f'Problem with id {problem_id} does not exist')
        else:
            return problem

@problems_blueprint.route('/<int:problem_id>', methods=['PUT'])
@jwt_required()
def modify_problem_status(problem_id):
    user_id = current_user['id']
    payload = request.get_json()
    should_reset = payload['reset']
    
    problem = get_problem(problem_id)
    if problem == None:
        abort(404, f'Problem with id {problem_id} does not exist')
    
    if should_reset: 
        reset_problem(user_id, problem_id)
        return {'msg': f'Problem with id {problem_id} reset'}
    else:
        return {'msg': 'No changes made'}

@problems_blueprint.route('/daily', methods=['GET'])
@jwt_required()
def get_daily_problems():
    user_id = current_user['id']

    daily_problems = get_problems_assigned_today(user_id)
    return jsonify(daily_problems)

@problems_blueprint.route('/', methods=['GET'])
@jwt_required(optional=True)
def get_all_problems():
    if current_user == None:
        problems = get_problems()
        return jsonify(problems)
    else:
        user_id = current_user['id']
        problems = get_problems_with_statistics(user_id)
        return jsonify(problems)

