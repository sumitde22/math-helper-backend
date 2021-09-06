create or replace procedure delete_user(user_id_param int) 
language plpgsql
as 
$$
begin
  DELETE FROM user_attempt_log WHERE user_id = user_id_param;
  DELETE FROM daily_assignment WHERE user_id = user_id_param;
  DELETE FROM interval_calculation_info WHERE user_id = user_id_param;
  DELETE FROM user_info WHERE id = user_id_param;
  commit;
end;
$$;

create or replace procedure reset_user(user_id_param int)
language plpgsql
as 
$$
declare
  max_questions constant int := 10;
begin
  DELETE FROM user_attempt_log WHERE user_id = user_id_param;
  DELETE FROM daily_assignment WHERE user_id = user_id_param;
  UPDATE interval_calculation_info SET correct_streak = 0, last_graduated_interval = NULL, earliest_calculated_due_date = CURRENT_DATE + 1 + ((problem_id - 1) / max_questions) WHERE user_id = user_id_param;
  commit;
end;
$$; 
  
create or replace function initialize_interval_calculation_table() 
returns trigger
language plpgsql
as
$$
declare
  max_questions constant int := 10;
begin
  INSERT INTO interval_calculation_info(problem_id, user_id, correct_streak, earliest_calculated_due_date) SELECT problem_info.id, NEW.id, 0, CURRENT_DATE + ((problem_info.id - 1) / max_questions) FROM problem_info;
  RETURN NEW;
end;
$$;

create or replace procedure assign_daily_questions(user_id_param int)
language plpgsql
as 
$$
declare
  max_questions constant numeric := 10;
begin
  DELETE FROM daily_assignment WHERE daily_assignment.date!=CURRENT_DATE;
  if NOT EXISTS (SELECT 1 FROM daily_assignment WHERE user_id=user_id_param) then
    INSERT INTO daily_assignment (problem_id, user_id, date, solved) 
    SELECT problem_id, user_id, CURRENT_DATE, false FROM interval_calculation_info WHERE earliest_calculated_due_date <= CURRENT_DATE AND user_id = user_id_param 
    ORDER BY earliest_calculated_due_date, correct_streak, problem_id LIMIT max_questions;
  end if;
  commit;
end;
$$;

create or replace function schedule_next_assignment() 
returns trigger 
language plpgsql
as 
$$
declare
  max_interval constant int := 365;
begin
  if EXISTS (SELECT 1 FROM daily_assignment WHERE date=CURRENT_DATE AND problem_id=NEW.problem_id AND user_id=NEW.user_id AND solved=false) then
    if NEW.correct then
      UPDATE interval_calculation_info 
        SET correct_streak = correct_streak + 1, 
        last_graduated_interval = CASE WHEN correct_streak > 2 THEN LEAST(last_graduated_interval * 2, max_interval) WHEN correct_streak = 2 THEN 4 ELSE NULL END, 
        earliest_calculated_due_date = GREATEST(earliest_calculated_due_date, CURRENT_DATE) + 
          CASE WHEN correct_streak > 2 THEN LEAST(last_graduated_interval * 2, max_interval) WHEN correct_streak = 2 THEN 4 WHEN correct_streak = 1 THEN 2 ELSE 1 END
               WHERE problem_id=NEW.problem_id AND user_id=NEW.user_id;
      UPDATE daily_assignment SET solved=true WHERE problem_id=NEW.problem_id AND user_id=NEW.user_id;
    else
      UPDATE interval_calculation_info SET correct_streak = 0, earliest_calculated_due_date = CURRENT_DATE WHERE problem_id=NEW.problem_id AND user_id=NEW.user_id;
    end if;
  end if;
  RETURN NEW;
end;
$$;

create or replace procedure reset_problem_statistics(user_id_param int, problem_id_param int)
language plpgsql
as 
$$
begin
  DELETE FROM user_attempt_log WHERE user_id=user_id_param AND problem_id=problem_id_param;
  UPDATE interval_calculation_info SET correct_streak=0, last_graduated_interval=NULL, earliest_calculated_due_date=CURRENT_DATE + 1 WHERE user_id=user_id_param AND problem_id=problem_id_param;
  commit;
end;
$$;

DROP TRIGGER IF EXISTS initialize_problem_assignments on public.user_info;

CREATE TRIGGER initialize_problem_assignments AFTER INSERT ON user_info FOR EACH ROW EXECUTE PROCEDURE initialize_interval_calculation_table();

DROP TRIGGER IF EXISTS calculate_intervals on public.user_attempt_log;

CREATE TRIGGER calculate_intervals AFTER INSERT ON user_attempt_log FOR EACH ROW EXECUTE FUNCTION schedule_next_assignment();