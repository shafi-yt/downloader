program calc_cross_products
    implicit none
    integer, parameter :: SIZE = 3 
    real, dimension(SIZE) :: v1, v2, cross_products 

    ! Get the first vector 
    write (*, 1000)
    1000 format (' Calculate the cross product of 2 vectors. ', &
                /,1x,' Enter first vector (three terms): ')
    read (*,*) v1 

    ! Get the second vector 
    write (*, 1010) 
    1010 format (1x, ' Enter second vector (three terms): ')
    read (*,*) v2

    ! Calculate the cross product of the two vecotors
    cross_products(1) = v1(2) * v2(3) - v1(3) * v2(2)
    cross_products(2) = v1(3) * v2(1) - v1(1) * v2(3) 
    cross_products(3) = v1(1) * v2(2) - v1(2) * v2(1)

    ! Tell user the result 
    write (*, 1020) cross_products
    1020 format (1x, ' The cross product is: ', &
     F10.1, 'i + ', F10.1, 'j + ', F10.1, 'k')
end program calc_cross_products