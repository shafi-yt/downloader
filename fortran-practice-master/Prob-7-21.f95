program calculate_min_max
    implicit none
    real :: first_value = -1.0, last_value = 3.0, xmin, min_value, &
            xmax, max_value 
    integer :: num_steps = 200
    ! The function `f` is defined in the CONTAINS section below.
    ! Do not declare it here; the contained function provides the
    ! correct explicit interface automatically.

    call min_max(first_value, last_value, num_steps, f, xmin, min_value, xmax, max_value)

    write (*, 100) xmin, min_value, xmax, max_value 
    100 format(/, 1x, 'Min value occured at x = ', F10.5,/, ' Min value              = ', F12.5,/, &
               1x, 'Max value occured at x = ', F10.5,/, ' Max value              = ', F12.5,/)

    CONTAINS 

    subroutine min_max(first_value, last_value, num_steps, func, xmin, min_value, xmax, max_value)
        real, intent(in) :: first_value, last_value
        integer, intent(in) :: num_steps 
        real, intent(out) :: xmin, min_value, xmax, max_value
        real, external :: func

        integer :: i 
        real :: step_size, temp
        real :: minimum = huge(0.0), maximum = -huge(0.0)

        step_size = (last_value - first_value) / real(num_steps)
        
        do i = 1, num_steps
            temp = func(first_value + real(i) * step_size)

            if (temp < minimum) then 
                minimum = temp 
                xmin = first_value + i * step_size
            else if (temp > maximum) then 
                maximum = temp 
                xmax = first_value + i * step_size
            end if 

            min_value = minimum 
            max_value = maximum

        end do

    end subroutine min_max


    function f(x) result(retval)
        real, intent(in) :: x
        real :: retval

        retval = (x**3 - 5.0*x**2 + 5.0*x + 2.0)
    end function f
end program calculate_min_max