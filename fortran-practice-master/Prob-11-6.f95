module dbl_precision_mod
    implicit none
    integer, parameter :: dbl = selected_real_kind(p=13)

contains
    
end module dbl_precision_mod

subroutine derivative(func, x_0, dx, deriv, error)
    use dbl_precision_mod 
    implicit none 

    real(kind=dbl), external :: func
    real(kind=dbl), intent(in) :: x_0, dx
    real(kind=dbl), intent(out) :: deriv
    integer, intent(out) :: error

    if (dx <= 0.0) then 
        error = 1
    else 
        error = 0

        deriv = (func(x_0 + dx) - func(x_0)) / real(dx)
    end if 
end subroutine derivative

function f(x)
    use dbl_precision_mod
    implicit none
    real(kind=dbl) :: x 
    real(kind=dbl) :: f 
    f = 10*dsin(20.0_dbl*x)
end function f

program test_program
    use dbl_precision_mod
    implicit none
    real(kind=dbl) :: x_0, dx, deriv
    real(kind=dbl), external :: f 
    integer :: error 

    dx = 0.0001_dbl
    x_0 = 0.0_dbl
    
    call derivative(f, x_0, dx, deriv, error)
    if (error /= 1) then 
        write (*,100) deriv
        100 format(1x, 'Derivative of function f(x) = 10 sin 20x = ', F16.7)
    else
        stop
    end if 
end program test_program